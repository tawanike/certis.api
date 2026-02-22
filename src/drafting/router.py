from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import require_tenant_matter
from src.drafting.schemas import ClaimGraph, ClaimGraphVersionResponse, EditClaimRequest, AddClaimRequest
from src.artifacts.models import ClaimGraphVersion
from src.matter.models import Matter, MatterState
from src.drafting.service import DraftingService

router = APIRouter(prefix="/matters", tags=["drafting"])


class GenerateClaimsRequest(BaseModel):
    brief_version_id: Optional[UUID] = None


@router.post("/{matter_id}/claims/generate", response_model=ClaimGraph)
async def generate_claims_endpoint(
    matter_id: UUID,
    request: GenerateClaimsRequest,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
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
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
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
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ClaimGraphVersion).where(
        ClaimGraphVersion.matter_id == matter_id
    ).order_by(desc(ClaimGraphVersion.version_number))

    result = await db.execute(stmt)
    return result.scalars().all()


async def _require_editable_matter(matter_id: UUID, db: AsyncSession) -> None:
    matter = await db.get(Matter, matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    allowed = {MatterState.CLAIMS_PROPOSED, MatterState.CLAIMS_APPROVED}
    if matter.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Claims editing is only allowed when matter is in CLAIMS_PROPOSED or CLAIMS_APPROVED (current: {matter.status.value})",
        )


@router.patch(
    "/{matter_id}/claims/{version_id}/nodes/{node_id}",
    response_model=ClaimGraphVersionResponse,
)
async def edit_claim_endpoint(
    matter_id: UUID,
    version_id: UUID,
    node_id: str,
    request: EditClaimRequest,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    await _require_editable_matter(matter_id, db)
    service = DraftingService(db)
    try:
        result = await service.edit_claim(matter_id, version_id, node_id, request, current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{matter_id}/claims/{version_id}/nodes",
    response_model=ClaimGraphVersionResponse,
)
async def add_claim_endpoint(
    matter_id: UUID,
    version_id: UUID,
    request: AddClaimRequest,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    await _require_editable_matter(matter_id, db)
    service = DraftingService(db)
    try:
        result = await service.add_claim(matter_id, version_id, request, current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{matter_id}/claims/{version_id}/nodes/{node_id}",
    response_model=ClaimGraphVersionResponse,
)
async def delete_claim_endpoint(
    matter_id: UUID,
    version_id: UUID,
    node_id: str,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    await _require_editable_matter(matter_id, db)
    service = DraftingService(db)
    try:
        result = await service.delete_claim(matter_id, version_id, node_id, current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
