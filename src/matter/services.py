from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from fastapi import HTTPException, status
from src.matter.models import Matter, MatterState, matter_jurisdictions, JurisdictionEnum
from src.auth.models import User, Tenant
from src.matter.schemas import MatterCreate, MatterUpdate

class MatterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_jurisdictions(self, matter_id: UUID) -> list[str]:
        result = await self.db.execute(
            select(matter_jurisdictions.c.jurisdiction)
            .where(matter_jurisdictions.c.matter_id == matter_id)
        )
        return [row[0].value if hasattr(row[0], 'value') else str(row[0]) for row in result.fetchall()]

    async def _set_jurisdictions(self, matter_id: UUID, jurisdictions: list[JurisdictionEnum]):
        # Clear existing jurisdictions
        await self.db.execute(
            delete(matter_jurisdictions).where(matter_jurisdictions.c.matter_id == matter_id)
        )
        # Insert new ones
        if jurisdictions:
            await self.db.execute(
                insert(matter_jurisdictions),
                [{"matter_id": matter_id, "jurisdiction": j} for j in jurisdictions]
            )

    async def create_matter(self, matter_in: MatterCreate, tenant_id: UUID, attorney_id: UUID) -> dict:
        matter = Matter(
            title=matter_in.title,
            reference_number=matter_in.reference_number,
            description=matter_in.description,
            tenant_id=tenant_id,
            attorney_id=attorney_id,
            status=MatterState.CREATED
        )
        self.db.add(matter)
        await self.db.flush()  # Get the ID before committing

        # Set jurisdictions
        await self._set_jurisdictions(matter.id, matter_in.jurisdictions)
        
        await self.db.commit()
        await self.db.refresh(matter)
        
        # Build response with jurisdictions
        jurisdictions = await self._get_jurisdictions(matter.id)
        return {**matter.__dict__, "jurisdictions": jurisdictions}

    async def get_matter(self, matter_id: UUID, tenant_id: UUID = None) -> dict:
        query = select(Matter).filter(Matter.id == matter_id)
        if tenant_id:
            query = query.filter(Matter.tenant_id == tenant_id)
        result = await self.db.execute(query)
        matter = result.scalars().first()
        if not matter:
            raise HTTPException(status_code=404, detail="Matter not found")

        jurisdictions = await self._get_jurisdictions(matter_id)
        return {**matter.__dict__, "jurisdictions": jurisdictions}

    async def list_matters(self, tenant_id: UUID, skip: int = 0, limit: int = 100) -> list[dict]:
        result = await self.db.execute(
            select(Matter).filter(Matter.tenant_id == tenant_id).offset(skip).limit(limit)
        )
        matters = result.scalars().all()
        
        # Attach jurisdictions to each matter
        enriched = []
        for m in matters:
            jurisdictions = await self._get_jurisdictions(m.id)
            enriched.append({**m.__dict__, "jurisdictions": jurisdictions})
        return enriched

    async def update_status(self, matter_id: UUID, new_status: MatterState) -> dict:
        matter_dict = await self.get_matter(matter_id)
        matter_result = await self.db.execute(select(Matter).filter(Matter.id == matter_id))
        matter = matter_result.scalars().first()
        
        current_status = matter.status
        
        # Deterministic State Machine Logic
        valid_transitions = {
            MatterState.CREATED: [MatterState.BRIEF_ANALYZED],
            MatterState.BRIEF_ANALYZED: [MatterState.CLAIMS_PROPOSED],
            MatterState.CLAIMS_PROPOSED: [MatterState.CLAIMS_APPROVED, MatterState.BRIEF_ANALYZED],
            MatterState.CLAIMS_APPROVED: [MatterState.RISK_REVIEWED, MatterState.SPEC_GENERATED],
            MatterState.RISK_REVIEWED: [MatterState.SPEC_GENERATED, MatterState.CLAIMS_APPROVED],
            MatterState.SPEC_GENERATED: [MatterState.QA_COMPLETE],
            MatterState.QA_COMPLETE: [MatterState.LOCKED_FOR_EXPORT, MatterState.SPEC_GENERATED],
            MatterState.LOCKED_FOR_EXPORT: []
        }

        if new_status not in valid_transitions.get(current_status, []):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid transition from {current_status} to {new_status}"
            )

        matter.status = new_status
        await self.db.commit()
        await self.db.refresh(matter)
        
        jurisdictions = await self._get_jurisdictions(matter_id)
        return {**matter.__dict__, "jurisdictions": jurisdictions}
