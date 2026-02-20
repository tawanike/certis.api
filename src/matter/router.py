from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.matter.schemas import MatterCreate, MatterResponse, MatterState
from src.matter.services import MatterService

router = APIRouter(prefix="/matters", tags=["matters"])

# Dummy IDs for MVP until Auth is implemented
DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000002")

@router.post("", response_model=MatterResponse)
async def create_matter(matter: MatterCreate, db: AsyncSession = Depends(get_db)):
    service = MatterService(db)
    return await service.create_matter(matter, DEMO_TENANT_ID, DEMO_USER_ID)

@router.get("", response_model=List[MatterResponse])
async def list_matters(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    service = MatterService(db)
    return await service.list_matters(DEMO_TENANT_ID, skip, limit)

@router.get("/{matter_id}", response_model=MatterResponse)
async def get_matter(matter_id: UUID, db: AsyncSession = Depends(get_db)):
    service = MatterService(db)
    return await service.get_matter(matter_id)

@router.patch("/{matter_id}/status", response_model=MatterResponse)
async def update_matter_status(matter_id: UUID, status: MatterState, db: AsyncSession = Depends(get_db)):
    service = MatterService(db)
    return await service.update_status(matter_id, status)
