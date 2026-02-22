from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import require_tenant_matter
from src.qa.schemas import QAReport, QAReportVersionResponse
from src.qa.models import QAReportVersion
from src.qa.service import QAService

router = APIRouter(prefix="/matters", tags=["qa"])


class ValidateQARequest(BaseModel):
    claim_version_id: Optional[UUID] = None
    spec_version_id: Optional[UUID] = None


@router.post("/{matter_id}/qa/validate", response_model=QAReport)
async def validate_qa_endpoint(
    matter_id: UUID,
    request: ValidateQARequest,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = QAService(db)
    try:
        result = await service.run_qa_validation(
            matter_id, request.claim_version_id, request.spec_version_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{matter_id}/qa/{version_id}/commit", response_model=QAReportVersionResponse)
async def commit_qa_version_endpoint(
    matter_id: UUID,
    version_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = QAService(db)
    try:
        result = await service.commit_version(matter_id, version_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{matter_id}/qa/versions", response_model=List[QAReportVersionResponse])
async def list_qa_versions(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(QAReportVersion)
        .where(QAReportVersion.matter_id == matter_id)
        .order_by(desc(QAReportVersion.version_number))
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{matter_id}/qa/{version_id}", response_model=QAReportVersionResponse)
async def get_qa_version(
    matter_id: UUID,
    version_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(QAReportVersion).where(
        QAReportVersion.id == version_id,
        QAReportVersion.matter_id == matter_id,
    )
    result = await db.execute(stmt)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="QA report version not found")
    return version
