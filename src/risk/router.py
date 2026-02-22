from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import require_tenant_matter
from src.risk.schemas import RiskAnalysis, RiskAnalysisVersionResponse
from src.risk.models import RiskAnalysisVersion
from src.risk.service import RiskService

router = APIRouter(prefix="/matters", tags=["risk"])


class AnalyzeRiskRequest(BaseModel):
    claim_version_id: Optional[UUID] = None


@router.post("/{matter_id}/risk/analyze", response_model=RiskAnalysis)
async def analyze_risk_endpoint(
    matter_id: UUID,
    request: AnalyzeRiskRequest,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = RiskService(db)
    try:
        result = await service.generate_risk_analysis(matter_id, request.claim_version_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{matter_id}/risk/{version_id}/commit", response_model=RiskAnalysisVersionResponse)
async def commit_risk_version_endpoint(
    matter_id: UUID,
    version_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = RiskService(db)
    try:
        result = await service.commit_version(matter_id, version_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{matter_id}/risk/versions", response_model=List[RiskAnalysisVersionResponse])
async def list_risk_versions(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(RiskAnalysisVersion)
        .where(RiskAnalysisVersion.matter_id == matter_id)
        .order_by(desc(RiskAnalysisVersion.version_number))
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{matter_id}/risk/{version_id}", response_model=RiskAnalysisVersionResponse)
async def get_risk_version(
    matter_id: UUID,
    version_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(RiskAnalysisVersion).where(
        RiskAnalysisVersion.id == version_id,
        RiskAnalysisVersion.matter_id == matter_id,
    )
    result = await db.execute(stmt)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Risk analysis version not found")
    return version
