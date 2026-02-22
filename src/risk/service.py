import logging
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from src.risk.schemas import RiskAnalysis
from src.risk.models import RiskAnalysisVersion
from src.artifacts.claims.models import ClaimGraphVersion
from src.artifacts.specs.models import SpecVersion
from src.matter.models import Matter, MatterState
from src.workstreams.models import Workstream, WorkstreamTypeEnum
from src.agents.risk.agent import risk_agent, RiskAgentState
from src.agents.risk.re_evaluation_agent import risk_re_evaluation_agent, ReEvalAgentState
from src.documents.service import DocumentService

logger = logging.getLogger(__name__)


class RiskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_claims_text(self, matter_id: UUID, claim_version_id: Optional[UUID] = None) -> tuple[str, UUID]:
        """
        Fetch claims from the DB and format as text for the risk agent.
        Returns (formatted_text, claim_version_id).
        """
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
            # Require an authoritative (approved) claim version
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
                    "The attorney must approve the claims before running risk analysis."
                )

        return self._format_claims(version.graph_data), version.id

    def _format_claims(self, graph_data: dict) -> str:
        """Format structured claim graph data into text the risk agent can consume."""
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

    async def _retrieve_document_context(self, matter_id: UUID, query_text: str) -> str:
        """Retrieve relevant document chunks as context for the agent."""
        try:
            doc_service = DocumentService(self.db)
            chunks = await doc_service.search_chunks(matter_id, query_text, top_k=6)
            return DocumentService.format_chunks_as_context(chunks)
        except Exception as e:
            logger.warning(f"RAG retrieval failed for matter {matter_id}: {e}")
            return ""

    async def generate_risk_analysis(
        self, matter_id: UUID, claim_version_id: Optional[UUID] = None
    ) -> RiskAnalysis:
        """
        Invokes the Risk Analysis Agent to analyze claims for litigation
        vulnerabilities and saves the result as a non-authoritative proposal.
        """
        # 1. Fetch claims text
        claim_text, resolved_claim_version_id = await self._get_claims_text(
            matter_id, claim_version_id
        )

        # 1b. Retrieve document context via RAG
        document_context = await self._retrieve_document_context(
            matter_id, claim_text[:500]
        )

        # 2. Invoke Agent
        initial_state: RiskAgentState = {
            "claim_text": claim_text,
            "document_context": document_context,
            "risk_analysis": None,
            "messages": [],
            "errors": [],
        }

        final_state = await risk_agent.ainvoke(initial_state)

        if final_state.get("errors"):
            raise ValueError(f"Agent failed: {final_state['errors']}")

        risk_analysis: RiskAnalysis = final_state["risk_analysis"]

        # 3. Determine Version Number
        stmt = (
            select(RiskAnalysisVersion)
            .where(RiskAnalysisVersion.matter_id == matter_id)
            .order_by(desc(RiskAnalysisVersion.version_number))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        latest_version = result.scalar_one_or_none()
        next_version = (latest_version.version_number + 1) if latest_version else 1

        # 4. Persist as Proposal (Non-Authoritative)
        proposal = RiskAnalysisVersion(
            matter_id=matter_id,
            version_number=next_version,
            description="AI Generated Risk Analysis",
            analysis_data=risk_analysis.model_dump(),
            is_authoritative=False,
            claim_version_id=resolved_claim_version_id,
        )
        self.db.add(proposal)
        await self.db.flush()

        # 5. Update Matter defensibility_score
        matter = await self.db.get(Matter, matter_id)
        if matter:
            matter.defensibility_score = risk_analysis.defensibility_score

        # 6. Update Workstream pointer
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_risk_version_id = proposal.id

        await self.db.commit()
        await self.db.refresh(proposal)

        return risk_analysis

    async def _get_spec_text(self, matter_id: UUID, spec_version_id: Optional[UUID] = None) -> tuple[str, UUID]:
        """
        Fetch spec from the DB and format as text for the re-evaluation agent.
        Returns (formatted_text, spec_version_id).
        """
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
                    "The specification must be generated and approved before re-evaluation."
                )

        return self._format_spec(version.content_data), version.id

    def _format_spec(self, content_data: dict) -> str:
        """Format structured spec content_data into text the agent can consume."""
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

    async def _get_previous_risk_findings(self, matter_id: UUID) -> str:
        """Fetch the latest authoritative risk analysis findings formatted as text."""
        result = await self.db.execute(
            select(RiskAnalysisVersion).where(
                RiskAnalysisVersion.matter_id == matter_id,
                RiskAnalysisVersion.is_authoritative == True,
            ).order_by(desc(RiskAnalysisVersion.version_number)).limit(1)
        )
        version = result.scalar_one_or_none()
        if not version:
            return "No previous risk analysis found."

        analysis = version.analysis_data
        parts = [f"Previous Defensibility Score: {analysis.get('defensibility_score', 'N/A')}"]
        for finding in analysis.get("findings", []):
            parts.append(
                f"- [{finding.get('id')}] {finding.get('category')} ({finding.get('severity')}): "
                f"{finding.get('title')} — {finding.get('description')}"
            )
        if analysis.get("summary"):
            parts.append(f"\nPrevious Summary: {analysis['summary']}")
        return "\n".join(parts)

    async def re_evaluate_risk_post_spec(
        self, matter_id: UUID, spec_version_id: Optional[UUID] = None
    ) -> RiskAnalysis:
        """
        Re-evaluates claims against the specification, comparing with previous
        risk findings to assess whether the spec has improved defensibility.
        """
        # 1. Fetch claims, spec, and previous findings
        claim_text, resolved_claim_version_id = await self._get_claims_text(matter_id)
        spec_text, resolved_spec_version_id = await self._get_spec_text(matter_id, spec_version_id)
        previous_risk_findings = await self._get_previous_risk_findings(matter_id)

        # 1b. Retrieve document context via RAG
        document_context = await self._retrieve_document_context(
            matter_id, claim_text[:300] + " specification structural support"
        )

        # 2. Invoke Re-Evaluation Agent
        initial_state: ReEvalAgentState = {
            "claim_text": claim_text,
            "spec_text": spec_text,
            "previous_risk_findings": previous_risk_findings,
            "document_context": document_context,
            "risk_analysis": None,
            "messages": [],
            "errors": [],
        }

        final_state = await risk_re_evaluation_agent.ainvoke(initial_state)

        if final_state.get("errors"):
            raise ValueError(f"Re-evaluation agent failed: {final_state['errors']}")

        risk_analysis: RiskAnalysis = final_state["risk_analysis"]

        # 3. Determine Version Number
        stmt = (
            select(RiskAnalysisVersion)
            .where(RiskAnalysisVersion.matter_id == matter_id)
            .order_by(desc(RiskAnalysisVersion.version_number))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        latest_version = result.scalar_one_or_none()
        next_version = (latest_version.version_number + 1) if latest_version else 1

        # 4. Persist as Proposal (Non-Authoritative) with spec_version_id
        proposal = RiskAnalysisVersion(
            matter_id=matter_id,
            version_number=next_version,
            description="AI Generated Risk Re-Evaluation (Post-Specification)",
            analysis_data=risk_analysis.model_dump(),
            is_authoritative=False,
            claim_version_id=resolved_claim_version_id,
            spec_version_id=resolved_spec_version_id,
        )
        self.db.add(proposal)
        await self.db.flush()

        # 5. Update Matter defensibility_score
        matter = await self.db.get(Matter, matter_id)
        if matter:
            matter.defensibility_score = risk_analysis.defensibility_score

        # 6. Update Workstream pointer
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_risk_version_id = proposal.id

        await self.db.commit()
        await self.db.refresh(proposal)

        return risk_analysis

    async def commit_version(self, matter_id: UUID, version_id: UUID) -> RiskAnalysisVersion:
        """
        Promotes a specific risk analysis version to authoritative
        and advances matter state to RISK_REVIEWED.
        """
        stmt = select(RiskAnalysisVersion).where(
            RiskAnalysisVersion.id == version_id,
            RiskAnalysisVersion.matter_id == matter_id,
        )
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()

        if not version:
            raise ValueError("Version not found")

        version.is_authoritative = True

        # Update Matter State
        matter = await self.db.get(Matter, matter_id)
        if matter:
            if matter.status == MatterState.CLAIMS_APPROVED:
                matter.status = MatterState.RISK_REVIEWED
            elif matter.status == MatterState.SPEC_GENERATED:
                matter.status = MatterState.RISK_RE_REVIEWED

        # Update Workstream pointer
        ws_result = await self.db.execute(
            select(Workstream).where(
                Workstream.matter_id == matter_id,
                Workstream.workstream_type == WorkstreamTypeEnum.DRAFTING_APPLICATION,
            ).limit(1)
        )
        workstream = ws_result.scalar_one_or_none()
        if workstream:
            workstream.active_risk_version_id = version.id

        await self.db.commit()
        await self.db.refresh(version)
        return version
