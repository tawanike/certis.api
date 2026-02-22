from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import require_tenant_matter
from src.specs.schemas import SpecDocument, SpecVersionResponse
from src.artifacts.specs.models import SpecVersion
from src.specs.service import SpecificationService

router = APIRouter(prefix="/matters", tags=["specifications"])


class GenerateSpecRequest(BaseModel):
    claim_version_id: Optional[UUID] = None
    risk_version_id: Optional[UUID] = None


@router.post("/{matter_id}/specifications/generate", response_model=SpecDocument)
async def generate_specification_endpoint(
    matter_id: UUID,
    request: GenerateSpecRequest,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = SpecificationService(db)
    try:
        result = await service.generate_specification(
            matter_id, request.claim_version_id, request.risk_version_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{matter_id}/specifications/{version_id}/commit", response_model=SpecVersionResponse)
async def commit_spec_version_endpoint(
    matter_id: UUID,
    version_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = SpecificationService(db)
    try:
        result = await service.commit_version(matter_id, version_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{matter_id}/specifications/versions", response_model=List[SpecVersionResponse])
async def list_spec_versions(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SpecVersion)
        .where(SpecVersion.matter_id == matter_id)
        .order_by(desc(SpecVersion.version_number))
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{matter_id}/specifications/{version_id}", response_model=SpecVersionResponse)
async def get_spec_version(
    matter_id: UUID,
    version_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SpecVersion).where(
        SpecVersion.id == version_id,
        SpecVersion.matter_id == matter_id,
    )
    result = await db.execute(stmt)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Specification version not found")
    return version
