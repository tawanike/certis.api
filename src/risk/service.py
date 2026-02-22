from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from src.risk.schemas import RiskAnalysis
from src.risk.models import RiskAnalysisVersion
from src.artifacts.claims.models import ClaimGraphVersion
from src.matter.models import Matter, MatterState
from src.workstreams.models import Workstream, WorkstreamTypeEnum
from src.agents.risk.agent import risk_agent, RiskAgentState


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

        # 2. Invoke Agent
        initial_state: RiskAgentState = {
            "claim_text": claim_text,
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

        # Update Matter State -> RISK_REVIEWED
        matter = await self.db.get(Matter, matter_id)
        if matter and matter.status == MatterState.CLAIMS_APPROVED:
            matter.status = MatterState.RISK_REVIEWED

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
