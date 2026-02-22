import json
import logging
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.drafting.schemas import ClaimGraph
from src.artifacts.models import ClaimGraphVersion
from src.artifacts.briefs.models import BriefVersion
from src.matter.models import Matter, MatterState
from src.workstreams.models import Workstream, WorkstreamTypeEnum
from src.agents.claims.agent import claims_agent
from src.agents.state import AgentState
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
        initial_state: AgentState = {
            "brief_text": brief_text,
            "document_context": document_context,
            "claim_graph": None,
            "messages": [],
            "errors": []
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

        await self.db.commit()
        await self.db.refresh(version)
        return version
