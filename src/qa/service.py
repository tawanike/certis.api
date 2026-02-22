import logging
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from src.qa.schemas import QAReport
from src.qa.models import QAReportVersion
from src.artifacts.briefs.models import BriefVersion
from src.artifacts.claims.models import ClaimGraphVersion
from src.artifacts.specs.models import SpecVersion
from src.matter.models import Matter, MatterState
from src.workstreams.models import Workstream, WorkstreamTypeEnum
from src.agents.qa.agent import qa_agent, QAAgentState
from src.documents.service import DocumentService

logger = logging.getLogger(__name__)


class QAService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_brief_text(self, matter_id: UUID) -> str:
        """Fetch the authoritative brief and format as text."""
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
                "The attorney must approve the brief before running QA validation."
            )
        return self._format_brief(brief.structure_data)

    def _format_brief(self, structure_data: dict) -> str:
        """Format the structured brief data into text."""
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
                    "The attorney must approve the claims before running QA validation."
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

    async def _get_spec_text(
        self, matter_id: UUID, spec_version_id: Optional[UUID] = None
    ) -> tuple[str, UUID]:
        """Fetch spec and format as text. Returns (text, spec_version_id)."""
        if spec_version_id:
            result = await self.db.execute(
                select(SpecVersion).where(
                    SpecVersion.id == spec_version_id,
                    SpecVersion.matter_id == matter_id,
                )
            )
            version = result.scalar_one_or_none()
            if not version:
                raise ValueError(f"Spec version {spec_version_id} not found for matter {matter_id}")
        else:
            result = await self.db.execute(
                select(SpecVersion).where(
                    SpecVersion.matter_id == matter_id,
                    SpecVersion.is_authoritative == True,
                ).order_by(desc(SpecVersion.version_number)).limit(1)
            )
            version = result.scalar_one_or_none()
            if not version:
                raise ValueError(
                    f"No authoritative specification found for matter {matter_id}. "
                    "The specification must be approved before running QA validation."
                )

        return self._format_spec(version.content_data), version.id

    def _format_spec(self, content_data: dict) -> str:
        """Format structured spec content_data into text."""
        parts = []
        for section_key, section_value in content_data.items():
            if isinstance(section_value, str):
                parts.append(f"## {section_key}\n{section_value}")
            elif isinstance(section_value, list):
                section_text = "\n".join(str(item) for item in section_value)
                parts.append(f"## {section_key}\n{section_text}")
            elif isinstance(section_value, dict):
                section_text = "\n".join(f"{k}: {v}" for k, v in section_value.items())
                parts.append(f"## {section_key}\n{section_text}")
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

    async def run_qa_validation(
        self,
        matter_id: UUID,
        claim_version_id: Optional[UUID] = None,
        spec_version_id: Optional[UUID] = None,
    ) -> QAReport:
        """
        Invokes the QA Agent to validate structural integrity of claims
        against the specification and saves the result as a non-authoritative proposal.
        """
        # 1. Fetch inputs
        brief_text = await self._get_brief_text(matter_id)
        claim_text, resolved_claim_version_id = await self._get_claims_text(
            matter_id, claim_version_id
        )
        spec_text, resolved_spec_version_id = await self._get_spec_text(
            matter_id, spec_version_id
        )

        # 1b. Retrieve document context via RAG
        document_context = await self._retrieve_document_context(
            matter_id, brief_text[:300] + " " + claim_text[:200]
        )

        # 2. Invoke Agent
        initial_state: QAAgentState = {
            "claim_text": claim_text,
            "spec_text": spec_text,
            "brief_text": brief_text,
            "document_context": document_context,
            "qa_report": None,
            "messages": [],
            "errors": [],
        }

        final_state = await qa_agent.ainvoke(initial_state)

        if final_state.get("errors"):
            raise ValueError(f"Agent failed: {final_state['errors']}")

        qa_report: QAReport = final_state["qa_report"]

        # 3. Determine Version Number
        stmt = (
            select(QAReportVersion)
            .where(QAReportVersion.matter_id == matter_id)
            .order_by(desc(QAReportVersion.version_number))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        latest_version = result.scalar_one_or_none()
        next_version = (latest_version.version_number + 1) if latest_version else 1

        # 4. Persist as Proposal (Non-Authoritative)
        proposal = QAReportVersion(
            matter_id=matter_id,
            version_number=next_version,
            description="AI Generated QA Validation",
            report_data=qa_report.model_dump(),
            is_authoritative=False,
            claim_version_id=resolved_claim_version_id,
            spec_version_id=resolved_spec_version_id,
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
            workstream.active_qa_version_id = proposal.id

        await self.db.commit()
        await self.db.refresh(proposal)

        return qa_report

    async def commit_version(self, matter_id: UUID, version_id: UUID) -> QAReportVersion:
        """
        Promotes a specific QA report version to authoritative
        and advances matter state to QA_COMPLETE.
        Rejects commit if the report has blocking errors (can_export == False).
        """
        stmt = select(QAReportVersion).where(
            QAReportVersion.id == version_id,
            QAReportVersion.matter_id == matter_id,
        )
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()

        if not version:
            raise ValueError("Version not found")

        # Enforce: cannot commit if there are blocking errors
        report_data = version.report_data
        if not report_data.get("can_export", False):
            raise ValueError(
                "Cannot commit QA report with blocking errors. "
                f"There are {report_data.get('total_errors', 0)} unresolved error(s). "
                "Resolve all errors and re-run QA validation before committing."
            )

        version.is_authoritative = True

        # Update Matter State
        matter = await self.db.get(Matter, matter_id)
        if matter and matter.status == MatterState.RISK_RE_REVIEWED:
            matter.status = MatterState.QA_COMPLETE

        # Update Workstream pointer
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_qa_version_id = version.id

        await self.db.commit()
        await self.db.refresh(version)
        return version
