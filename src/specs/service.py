import logging
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from typing import Dict, Any
from src.specs.schemas import SpecDocument, SpecParagraph, EditSpecParagraphRequest, AddSpecParagraphRequest
from src.artifacts.specs.models import SpecVersion
from src.artifacts.briefs.models import BriefVersion
from src.artifacts.claims.models import ClaimGraphVersion
from src.audit.models import AuditEvent, AuditEventType
from src.risk.models import RiskAnalysisVersion
from src.matter.models import Matter, MatterState
from src.workstreams.models import Workstream, WorkstreamTypeEnum
from src.agents.spec.agent import spec_agent, SpecAgentState
from src.documents.service import DocumentService

logger = logging.getLogger(__name__)


class SpecificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_brief_text(self, matter_id: UUID) -> str:
        """Fetch the authoritative brief and format as text for the spec agent."""
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
                "The attorney must approve the brief before generating specifications."
            )
        return self._format_brief(brief.structure_data)

    def _format_brief(self, structure_data: dict) -> str:
        """Format the structured brief data into text the spec agent can consume."""
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
                desc_text = c.get("description", "")
                optional = " (optional)" if c.get("optional") else ""
                parts.append(f"  - {name}{optional}: {desc_text}")

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

    async def _get_claims_text(
        self, matter_id: UUID, claim_version_id: Optional[UUID] = None
    ) -> tuple[str, UUID]:
        """Fetch claims and format as text. Returns (text, claim_version_id)."""
        if claim_version_id:
            result = await self.db.execute(
                select(ClaimGraphVersion).where(
                    ClaimGraphVersion.id == claim_version_id,
                    ClaimGraphVersion.matter_id == matter_id,
                )
            )
            version = result.scalar_one_or_none()
            if not version:
                raise ValueError(f"Claim version {claim_version_id} not found for matter {matter_id}")
        else:
            result = await self.db.execute(
                select(ClaimGraphVersion).where(
                    ClaimGraphVersion.matter_id == matter_id,
                    ClaimGraphVersion.is_authoritative == True,
                ).order_by(desc(ClaimGraphVersion.version_number)).limit(1)
            )
            version = result.scalar_one_or_none()
            if not version:
                raise ValueError(
                    f"No approved claims found for matter {matter_id}. "
                    "The attorney must approve the claims before generating specifications."
                )

        return self._format_claims(version.graph_data), version.id

    def _format_claims(self, graph_data: dict) -> str:
        """Format structured claim graph data into text."""
        parts = []
        nodes = graph_data.get("nodes", [])
        for node in nodes:
            claim_id = node.get("id", "?")
            claim_type = node.get("type", "unknown")
            claim_text = node.get("text", "")
            category = node.get("category", "")
            deps = node.get("dependencies", [])

            header = f"Claim {claim_id} ({claim_type}"
            if category:
                header += f", {category}"
            header += ")"
            if deps:
                header += f" [depends on: {', '.join(deps)}]"

            parts.append(f"{header}:\n{claim_text}")

        return "\n\n".join(parts)

    async def _get_risk_findings(
        self, matter_id: UUID, risk_version_id: Optional[UUID] = None
    ) -> tuple[str, UUID]:
        """Fetch risk analysis and format as text. Returns (text, risk_version_id)."""
        if risk_version_id:
            result = await self.db.execute(
                select(RiskAnalysisVersion).where(
                    RiskAnalysisVersion.id == risk_version_id,
                    RiskAnalysisVersion.matter_id == matter_id,
                )
            )
            version = result.scalar_one_or_none()
            if not version:
                raise ValueError(f"Risk version {risk_version_id} not found for matter {matter_id}")
        else:
            result = await self.db.execute(
                select(RiskAnalysisVersion).where(
                    RiskAnalysisVersion.matter_id == matter_id,
                    RiskAnalysisVersion.is_authoritative == True,
                ).order_by(desc(RiskAnalysisVersion.version_number)).limit(1)
            )
            version = result.scalar_one_or_none()
            if not version:
                raise ValueError(
                    f"No approved risk analysis found for matter {matter_id}. "
                    "The attorney must approve the risk analysis before generating specifications."
                )

        return self._format_risk_findings(version.analysis_data), version.id

    def _format_risk_findings(self, analysis_data: dict) -> str:
        """Format risk analysis data into text the spec agent can consume."""
        parts = []

        score = analysis_data.get("defensibility_score")
        if score is not None:
            parts.append(f"Defensibility Score: {score}/100")

        if summary := analysis_data.get("summary"):
            parts.append(f"Summary: {summary}")

        findings = analysis_data.get("findings", [])
        if findings:
            parts.append("Risk Findings:")
            for f in findings:
                finding_id = f.get("id", "?")
                claim_id = f.get("claim_id", "?")
                category = f.get("category", "unknown")
                severity = f.get("severity", "unknown")
                title = f.get("title", "")
                description = f.get("description", "")
                recommendation = f.get("recommendation", "")
                parts.append(
                    f"  {finding_id} (Claim {claim_id}, {category}, {severity}): "
                    f"{title}\n    {description}\n    Recommendation: {recommendation}"
                )

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

    async def generate_specification(
        self,
        matter_id: UUID,
        claim_version_id: Optional[UUID] = None,
        risk_version_id: Optional[UUID] = None,
    ) -> SpecDocument:
        """
        Invokes the Spec Drafting Agent to generate a patent specification
        and saves the result as a non-authoritative proposal.
        """
        # 1. Fetch inputs
        brief_text = await self._get_brief_text(matter_id)
        claim_text, resolved_claim_version_id = await self._get_claims_text(
            matter_id, claim_version_id
        )
        risk_findings, resolved_risk_version_id = await self._get_risk_findings(
            matter_id, risk_version_id
        )

        # 1b. Retrieve document context via RAG
        document_context = await self._retrieve_document_context(
            matter_id, brief_text[:300] + " " + claim_text[:200]
        )

        # 2. Invoke Agent
        initial_state: SpecAgentState = {
            "brief_text": brief_text,
            "claim_text": claim_text,
            "risk_findings": risk_findings,
            "document_context": document_context,
            "spec_document": None,
            "messages": [],
            "errors": [],
        }

        final_state = await spec_agent.ainvoke(initial_state)

        if final_state.get("errors"):
            raise ValueError(f"Agent failed: {final_state['errors']}")

        spec_document: SpecDocument = final_state["spec_document"]

        # 3. Determine Version Number
        stmt = (
            select(SpecVersion)
            .where(SpecVersion.matter_id == matter_id)
            .order_by(desc(SpecVersion.version_number))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        latest_version = result.scalar_one_or_none()
        next_version = (latest_version.version_number + 1) if latest_version else 1

        # 4. Persist as Proposal (Non-Authoritative)
        proposal = SpecVersion(
            matter_id=matter_id,
            version_number=next_version,
            description="AI Generated Specification",
            content_data=spec_document.model_dump(),
            is_authoritative=False,
            claim_version_id=resolved_claim_version_id,
            risk_version_id=resolved_risk_version_id,
        )
        self.db.add(proposal)
        await self.db.flush()

        # 5. Update Workstream pointer
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_spec_version_id = proposal.id

        # Audit event
        self.db.add(AuditEvent(
            matter_id=matter_id,
            event_type=AuditEventType.SPEC_GENERATED,
            actor_id=None,
            artifact_version_id=proposal.id,
            artifact_type="spec",
        ))

        await self.db.commit()
        await self.db.refresh(proposal)

        return spec_document

    async def commit_version(self, matter_id: UUID, version_id: UUID) -> SpecVersion:
        """
        Promotes a specific spec version to authoritative
        and advances matter state to SPEC_GENERATED.
        """
        stmt = select(SpecVersion).where(
            SpecVersion.id == version_id,
            SpecVersion.matter_id == matter_id,
        )
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()

        if not version:
            raise ValueError("Version not found")

        version.is_authoritative = True

        # Update Matter State -> SPEC_GENERATED
        matter = await self.db.get(Matter, matter_id)
        if matter and matter.status == MatterState.RISK_REVIEWED:
            matter.status = MatterState.SPEC_GENERATED

        # Update Workstream pointer
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_spec_version_id = version.id

        # Audit event
        self.db.add(AuditEvent(
            matter_id=matter_id,
            event_type=AuditEventType.SPEC_COMMITTED,
            actor_id=None,
            artifact_version_id=version.id,
            artifact_type="spec",
        ))

        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def _fetch_source_spec_version(self, matter_id: UUID, version_id: UUID) -> SpecVersion:
        stmt = select(SpecVersion).where(
            SpecVersion.id == version_id,
            SpecVersion.matter_id == matter_id,
        )
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()
        if not version:
            raise ValueError("Spec version not found")
        return version

    def _rebuild_claim_coverage(self, sections: list) -> Dict[str, list]:
        coverage: Dict[str, list] = {}
        for para in sections:
            for ref in para.get("claim_references", []):
                if ref not in coverage:
                    coverage[ref] = []
                coverage[ref].append(para["id"])
        return coverage

    async def _clone_and_save_spec_version(
        self,
        matter_id: UUID,
        content_data: dict,
        description: str,
        actor_id: Optional[UUID],
        detail: Dict[str, Any],
        source_version: SpecVersion,
    ) -> SpecVersion:
        # Rebuild claim_coverage from sections
        content_data["claim_coverage"] = self._rebuild_claim_coverage(content_data.get("sections", []))

        # Determine next version number
        stmt = (
            select(SpecVersion)
            .where(SpecVersion.matter_id == matter_id)
            .order_by(desc(SpecVersion.version_number))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        latest = result.scalar_one_or_none()
        next_version = (latest.version_number + 1) if latest else 1

        proposal = SpecVersion(
            matter_id=matter_id,
            version_number=next_version,
            description=description,
            content_data=content_data,
            is_authoritative=False,
            claim_version_id=source_version.claim_version_id,
            risk_version_id=source_version.risk_version_id,
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
            workstream.active_spec_version_id = proposal.id

        # Audit event
        self.db.add(AuditEvent(
            matter_id=matter_id,
            event_type=AuditEventType.SPEC_EDITED,
            actor_id=actor_id,
            artifact_version_id=proposal.id,
            artifact_type="spec",
            detail=detail,
        ))

        await self.db.commit()
        await self.db.refresh(proposal)
        return proposal

    async def edit_paragraph(
        self,
        matter_id: UUID,
        version_id: UUID,
        paragraph_id: str,
        patch: EditSpecParagraphRequest,
        actor_id: Optional[UUID] = None,
    ) -> SpecVersion:
        source = await self._fetch_source_spec_version(matter_id, version_id)
        content = dict(source.content_data)
        sections = list(content.get("sections", []))

        target = next((p for p in sections if p["id"] == paragraph_id), None)
        if not target:
            raise ValueError(f"Paragraph '{paragraph_id}' not found")

        updates = patch.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("No fields provided for edit")

        for field, value in updates.items():
            target[field] = value

        content["sections"] = sections
        return await self._clone_and_save_spec_version(
            matter_id, content,
            f"Edited paragraph {paragraph_id}",
            actor_id,
            {"operation": "edit", "paragraph_id": paragraph_id, "changes": updates},
            source,
        )

    async def add_paragraph(
        self,
        matter_id: UUID,
        version_id: UUID,
        request: AddSpecParagraphRequest,
        actor_id: Optional[UUID] = None,
    ) -> SpecVersion:
        source = await self._fetch_source_spec_version(matter_id, version_id)
        content = dict(source.content_data)
        sections = list(content.get("sections", []))

        # Assign next paragraph ID
        existing_ids = []
        for p in sections:
            pid = p.get("id", "")
            if pid.startswith("P"):
                try:
                    existing_ids.append(int(pid[1:]))
                except ValueError:
                    pass
        next_id = f"P{max(existing_ids, default=0) + 1}"

        new_para = {
            "id": next_id,
            "section": request.section,
            "text": request.text,
            "claim_references": request.claim_references,
        }

        # Insert after specified paragraph, or at end
        if request.after_paragraph_id:
            idx = next((i for i, p in enumerate(sections) if p["id"] == request.after_paragraph_id), None)
            if idx is not None:
                sections.insert(idx + 1, new_para)
            else:
                sections.append(new_para)
        else:
            sections.append(new_para)

        content["sections"] = sections
        return await self._clone_and_save_spec_version(
            matter_id, content,
            f"Added paragraph {next_id}",
            actor_id,
            {"operation": "add", "paragraph_id": next_id},
            source,
        )

    async def delete_paragraph(
        self,
        matter_id: UUID,
        version_id: UUID,
        paragraph_id: str,
        actor_id: Optional[UUID] = None,
    ) -> SpecVersion:
        source = await self._fetch_source_spec_version(matter_id, version_id)
        content = dict(source.content_data)
        sections = list(content.get("sections", []))

        if not any(p["id"] == paragraph_id for p in sections):
            raise ValueError(f"Paragraph '{paragraph_id}' not found")

        sections = [p for p in sections if p["id"] != paragraph_id]

        # Renumber paragraphs sequentially
        for idx, para in enumerate(sections, start=1):
            para["id"] = f"P{idx}"

        content["sections"] = sections
        return await self._clone_and_save_spec_version(
            matter_id, content,
            f"Deleted paragraph {paragraph_id}",
            actor_id,
            {"operation": "delete", "paragraph_id": paragraph_id},
            source,
        )
