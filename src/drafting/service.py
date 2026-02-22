import json
import logging
from collections import deque
from uuid import UUID
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.drafting.schemas import ClaimGraph, ClaimNode, EditClaimRequest, AddClaimRequest, ClaimGraphVersionResponse
from src.artifacts.models import ClaimGraphVersion
from src.artifacts.briefs.models import BriefVersion
from src.audit.models import AuditEvent, AuditEventType
from src.matter.models import Matter, MatterState
from src.workstreams.models import Workstream, WorkstreamTypeEnum
from src.agents.claims.agent import claims_agent
from src.agents.state import ClaimsAgentState
from src.documents.service import DocumentService
from src.database import get_db

logger = logging.getLogger(__name__)

class DraftingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_brief_text(self, matter_id: UUID, brief_version_id: Optional[UUID] = None) -> str:
        """
        Fetch the brief's structured data from the DB and format it as text
        for the claims agent. If brief_version_id is provided, use that specific
        version; otherwise require an attorney-approved (authoritative) brief.
        """
        if brief_version_id:
            # Explicit version requested — use it regardless of approval status
            result = await self.db.execute(
                select(BriefVersion).where(
                    BriefVersion.id == brief_version_id,
                    BriefVersion.matter_id == matter_id,
                )
            )
            brief = result.scalar_one_or_none()
            if not brief:
                raise ValueError(f"Brief version {brief_version_id} not found for matter {matter_id}")
        else:
            # Require an approved brief
            result = await self.db.execute(
                select(BriefVersion).where(
                    BriefVersion.matter_id == matter_id,
                    BriefVersion.is_authoritative == True,
                ).order_by(desc(BriefVersion.version_number)).limit(1)
            )
            brief = result.scalar_one_or_none()

            if not brief:
                raise ValueError(
                    f"No approved brief found for matter {matter_id}. "
                    "The attorney must review and approve the brief before generating claims."
                )

        return self._format_brief_for_claims(brief.structure_data)

    def _format_brief_for_claims(self, structure_data: dict) -> str:
        """Format the structured brief data into text the claims agent can consume."""
        parts = []

        if inv := structure_data.get("core_invention_statement"):
            parts.append(f"Core Invention: {inv}")

        if field := structure_data.get("technical_field"):
            parts.append(f"Technical Field: {field}")

        if problem := structure_data.get("problem_statement"):
            parts.append(f"Problem: {problem}")

        if solution := structure_data.get("technical_solution_summary"):
            parts.append(f"Solution: {solution}")

        if components := structure_data.get("system_components"):
            parts.append("System Components:")
            for c in components:
                name = c.get("name", "Unknown")
                desc = c.get("description", "")
                optional = " (optional)" if c.get("optional") else ""
                parts.append(f"  - {name}{optional}: {desc}")

        if steps := structure_data.get("method_steps"):
            parts.append("Method Steps:")
            for s in steps:
                parts.append(f"  {s.get('step_id', '-')}. {s.get('description', '')}")

        if variants := structure_data.get("variants"):
            parts.append("Variants:")
            for v in variants:
                parts.append(f"  - {v.get('description', '')}")

        if effects := structure_data.get("technical_effects"):
            parts.append("Technical Effects:")
            for e in effects:
                parts.append(f"  - {e}")

        if data_elements := structure_data.get("data_elements"):
            parts.append("Data Elements:")
            for d in data_elements:
                parts.append(f"  - {d.get('name', '')}: {d.get('description', '')}")

        return "\n\n".join(parts)

    async def _retrieve_document_context(self, matter_id: UUID, query_text: str) -> str:
        """Retrieve relevant document chunks as context for the agent."""
        try:
            doc_service = DocumentService(self.db)
            chunks = await doc_service.search_chunks(matter_id, query_text, top_k=6)
            return DocumentService.format_chunks_as_context(chunks)
        except Exception as e:
            logger.warning(f"RAG retrieval failed for matter {matter_id}: {e}")
            return ""

    async def generate_claims(self, matter_id: UUID, brief_version_id: Optional[UUID] = None) -> ClaimGraph:
        """
        Invokes the Claims Architect Agent to generate a claim set
        from the structured brief data and saves it as a non-authoritative proposal.
        """
        # 1. Fetch brief data from DB
        brief_text = await self._get_brief_text(matter_id, brief_version_id)

        # 1b. Retrieve document context via RAG
        document_context = await self._retrieve_document_context(
            matter_id, brief_text[:500]
        )

        # 2. Invoke Agent
        initial_state: ClaimsAgentState = {
            "brief_text": brief_text,
            "document_context": document_context,
            "claim_graph": None,
            "messages": [],
            "errors": [],
            "canonical_model": None,
            "system_claim_nodes": None,
            "method_claim_nodes": None,
            "medium_claim_nodes": None,
            "all_independent_nodes": None,
            "scope_validation": None,
        }

        final_state = await claims_agent.ainvoke(initial_state)

        if final_state.get("errors"):
            raise ValueError(f"Agent failed: {final_state['errors']}")

        claim_graph = final_state["claim_graph"]

        # 3. Determine Version Number
        stmt = select(ClaimGraphVersion).where(
            ClaimGraphVersion.matter_id == matter_id
        ).order_by(desc(ClaimGraphVersion.version_number)).limit(1)

        result = await self.db.execute(stmt)
        latest_version = result.scalar_one_or_none()
        next_version = (latest_version.version_number + 1) if latest_version else 1

        # 4. Persist as Proposal (Non-Authoritative)
        proposal = ClaimGraphVersion(
            matter_id=matter_id,
            version_number=next_version,
            description="AI Generated Proposal",
            graph_data=claim_graph.model_dump(),
            is_authoritative=False
        )
        self.db.add(proposal)
        await self.db.flush()

        # 5. Update Matter State → CLAIMS_PROPOSED
        matter = await self.db.get(Matter, matter_id)
        if matter and matter.status == MatterState.BRIEF_ANALYZED:
            matter.status = MatterState.CLAIMS_PROPOSED

        # 6. Update Workstream pointer
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_claim_version_id = proposal.id

        # Audit event
        self.db.add(AuditEvent(
            matter_id=matter_id,
            event_type=AuditEventType.CLAIMS_GENERATED,
            actor_id=None,
            artifact_version_id=proposal.id,
            artifact_type="claims",
        ))

        await self.db.commit()
        await self.db.refresh(proposal)

        return claim_graph

    async def commit_version(self, matter_id: UUID, version_id: UUID) -> ClaimGraphVersion:
        """
        Promotes a specific version to be authoritative and advances matter state.
        """
        stmt = select(ClaimGraphVersion).where(
            ClaimGraphVersion.id == version_id,
            ClaimGraphVersion.matter_id == matter_id,
        )
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()

        if not version:
            raise ValueError("Version not found")

        version.is_authoritative = True

        # Update Matter State → CLAIMS_APPROVED
        matter = await self.db.get(Matter, matter_id)
        if matter and matter.status == MatterState.CLAIMS_PROPOSED:
            matter.status = MatterState.CLAIMS_APPROVED

        # Update Workstream pointer to the committed version
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_claim_version_id = version.id

        # Audit event
        self.db.add(AuditEvent(
            matter_id=matter_id,
            event_type=AuditEventType.CLAIMS_COMMITTED,
            actor_id=None,
            artifact_version_id=version.id,
            artifact_type="claims",
        ))

        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def _fetch_source_version(self, matter_id: UUID, version_id: UUID) -> ClaimGraphVersion:
        stmt = select(ClaimGraphVersion).where(
            ClaimGraphVersion.id == version_id,
            ClaimGraphVersion.matter_id == matter_id,
        )
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()
        if not version:
            raise ValueError("Source version not found")
        return version

    @staticmethod
    def _check_circular_dependencies(nodes: list[ClaimNode]) -> None:
        node_ids = {n.id for n in nodes}
        adj: dict[str, list[str]] = {n.id: list(n.dependencies) for n in nodes}
        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(nid: str) -> bool:
            visited.add(nid)
            in_stack.add(nid)
            for dep in adj.get(nid, []):
                if dep in in_stack:
                    return True
                if dep not in visited and dfs(dep):
                    return True
            in_stack.discard(nid)
            return False

        for nid in node_ids:
            if nid not in visited:
                if dfs(nid):
                    raise ValueError("Circular dependency detected in claim graph")

    async def _clone_and_save_version(
        self,
        matter_id: UUID,
        graph: ClaimGraph,
        description: str,
        actor_id: UUID,
        detail: Dict[str, Any],
    ) -> ClaimGraphVersion:
        # Determine next version number
        stmt = select(ClaimGraphVersion).where(
            ClaimGraphVersion.matter_id == matter_id
        ).order_by(desc(ClaimGraphVersion.version_number)).limit(1)
        result = await self.db.execute(stmt)
        latest = result.scalar_one_or_none()
        next_version = (latest.version_number + 1) if latest else 1

        # Create new non-authoritative version
        proposal = ClaimGraphVersion(
            matter_id=matter_id,
            version_number=next_version,
            description=description,
            graph_data=graph.model_dump(),
            is_authoritative=False,
        )
        self.db.add(proposal)
        await self.db.flush()

        # Update workstream pointer
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_claim_version_id = proposal.id

        # Audit event
        self.db.add(AuditEvent(
            matter_id=matter_id,
            event_type=AuditEventType.CLAIMS_EDITED,
            actor_id=actor_id,
            artifact_version_id=proposal.id,
            artifact_type="claims",
            detail=detail,
        ))

        # Reset state if approved
        matter = await self.db.get(Matter, matter_id)
        if matter and matter.status == MatterState.CLAIMS_APPROVED:
            matter.status = MatterState.CLAIMS_PROPOSED

        await self.db.commit()
        await self.db.refresh(proposal)
        return proposal

    async def edit_claim(
        self,
        matter_id: UUID,
        version_id: UUID,
        node_id: str,
        patch: EditClaimRequest,
        actor_id: UUID,
    ) -> ClaimGraphVersion:
        source = await self._fetch_source_version(matter_id, version_id)
        graph = ClaimGraph(**source.graph_data)

        # Find node
        target = next((n for n in graph.nodes if n.id == node_id), None)
        if not target:
            raise ValueError(f"Claim node '{node_id}' not found")

        # Ensure at least one field changes
        updates = patch.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("No fields provided for edit")

        # Validate dependencies if provided
        all_ids = {n.id for n in graph.nodes}
        if patch.dependencies is not None:
            for dep_id in patch.dependencies:
                if dep_id not in all_ids:
                    raise ValueError(f"Dependency '{dep_id}' does not exist")
                if dep_id == node_id:
                    raise ValueError("A claim cannot depend on itself")

        # Apply updates
        for field, value in updates.items():
            setattr(target, field, value)

        self._check_circular_dependencies(graph.nodes)

        return await self._clone_and_save_version(
            matter_id, graph,
            f"Edited claim {node_id}",
            actor_id,
            {"operation": "edit", "node_id": node_id, "changes": updates},
        )

    async def add_claim(
        self,
        matter_id: UUID,
        version_id: UUID,
        request: AddClaimRequest,
        actor_id: UUID,
    ) -> ClaimGraphVersion:
        source = await self._fetch_source_version(matter_id, version_id)
        graph = ClaimGraph(**source.graph_data)

        all_ids = {n.id for n in graph.nodes}

        # Validate dependencies
        for dep_id in request.dependencies:
            if dep_id not in all_ids:
                raise ValueError(f"Dependency '{dep_id}' does not exist")

        if request.type == "dependent" and not request.dependencies:
            raise ValueError("Dependent claims must have at least one dependency")

        # Assign next sequential ID
        existing_int_ids = []
        for n in graph.nodes:
            try:
                existing_int_ids.append(int(n.id))
            except ValueError:
                pass
        next_id = str(max(existing_int_ids, default=0) + 1)

        new_node = ClaimNode(
            id=next_id,
            type=request.type,
            text=request.text,
            category=request.category,
            dependencies=request.dependencies,
        )
        graph.nodes.append(new_node)

        self._check_circular_dependencies(graph.nodes)

        return await self._clone_and_save_version(
            matter_id, graph,
            f"Added claim {next_id}",
            actor_id,
            {"operation": "add", "node_id": next_id},
        )

    async def delete_claim(
        self,
        matter_id: UUID,
        version_id: UUID,
        node_id: str,
        actor_id: UUID,
    ) -> ClaimGraphVersion:
        source = await self._fetch_source_version(matter_id, version_id)
        graph = ClaimGraph(**source.graph_data)

        # Verify node exists
        if not any(n.id == node_id for n in graph.nodes):
            raise ValueError(f"Claim node '{node_id}' not found")

        # Remove the node
        graph.nodes = [n for n in graph.nodes if n.id != node_id]

        # Build renumber map: old_id -> new sequential id
        renumber_map: dict[str, str] = {}
        for idx, node in enumerate(graph.nodes, start=1):
            renumber_map[node.id] = str(idx)

        # Apply renumbering
        for node in graph.nodes:
            node.id = renumber_map[node.id]
            node.dependencies = [
                renumber_map[d] for d in node.dependencies if d in renumber_map
            ]
            if node.mirror_source:
                if node.mirror_source in renumber_map:
                    node.mirror_source = renumber_map[node.mirror_source]
                else:
                    node.mirror_source = None

        return await self._clone_and_save_version(
            matter_id, graph,
            f"Deleted claim {node_id}",
            actor_id,
            {"operation": "delete", "node_id": node_id, "renumber_map": renumber_map},
        )
