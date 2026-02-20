from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from src.database import get_db
from src.drafting.schemas import ClaimGraph, ClaimGraphVersionResponse
from src.artifacts.models import ClaimGraphVersion
from src.drafting.service import DraftingService
from pydantic import BaseModel

router = APIRouter(prefix="/matters", tags=["drafting"])

class GenerateClaimsRequest(BaseModel):
    brief_version_id: Optional[UUID] = None

@router.post("/{matter_id}/claims/generate", response_model=ClaimGraph)
async def generate_claims_endpoint(
    matter_id: UUID,
    request: GenerateClaimsRequest,
    db: AsyncSession = Depends(get_db)
):
    service = DraftingService(db)
    try:
        result = await service.generate_claims(matter_id, request.brief_version_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{matter_id}/claims/{version_id}/commit", response_model=ClaimGraphVersionResponse)
async def commit_claim_version_endpoint(
    matter_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    service = DraftingService(db)
    try:
        result = await service.commit_version(matter_id, version_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{matter_id}/claims/versions", response_model=List[ClaimGraphVersionResponse])
async def list_claim_versions(
    matter_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(ClaimGraphVersion).where(
        ClaimGraphVersion.matter_id == matter_id
    ).order_by(desc(ClaimGraphVersion.version_number))
    
    result = await db.execute(stmt)
    return result.scalars().all()
