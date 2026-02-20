from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user, require_tenant_matter
from src.matter.schemas import MatterCreate, MatterResponse, MatterState
from src.matter.services import MatterService

router = APIRouter(prefix="/matters", tags=["matters"])


@router.post("", response_model=MatterResponse)
async def create_matter(
    matter: MatterCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = MatterService(db)
    return await service.create_matter(matter, current_user.tenant_id, current_user.id)


@router.get("", response_model=List[MatterResponse])
async def list_matters(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = MatterService(db)
    return await service.list_matters(current_user.tenant_id, skip, limit)


@router.get("/{matter_id}", response_model=MatterResponse)
async def get_matter(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = MatterService(db)
    return await service.get_matter(matter_id)


@router.patch("/{matter_id}/status", response_model=MatterResponse)
async def update_matter_status(
    matter_id: UUID,
    status: MatterState,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = MatterService(db)
    return await service.update_status(matter_id, status)
