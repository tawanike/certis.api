from typing import List, Any, Dict, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict

from src.database import get_db
from src.briefing.service import BriefingService

router = APIRouter(prefix="/matters", tags=["briefing"])


class BriefVersionResponse(BaseModel):
    id: UUID
    matter_id: UUID
    version_number: int
    source_material_hash: Optional[str]
    is_authoritative: bool
    structure_data: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.post("/{matter_id}/briefs/upload")
async def upload_brief(
    matter_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    service = BriefingService(db)
    try:
        result = await service.process_brief_upload(matter_id, file)
        return {
            "id": result.id,
            "version_number": result.version_number,
            "is_authoritative": result.is_authoritative,
            "structure_data": result.structure_data,
            "message": "Brief analyzed successfully. Review the breakdown and approve to proceed."
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during processing")


@router.post("/{matter_id}/briefs/{version_id}/approve", response_model=BriefVersionResponse)
async def approve_brief(
    matter_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Attorney approves a brief version, confirming the structured breakdown is correct."""
    service = BriefingService(db)
    try:
        result = await service.approve_brief(matter_id, version_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{matter_id}/briefs/versions", response_model=List[BriefVersionResponse])
async def list_brief_versions(
    matter_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all brief versions for a matter."""
    service = BriefingService(db)
    return await service.list_brief_versions(matter_id)


@router.get("/{matter_id}/briefs/{version_id}", response_model=BriefVersionResponse)
async def get_brief_version(
    matter_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific brief version."""
    service = BriefingService(db)
    result = await service.get_brief_version(matter_id, version_id)
    if not result:
        raise HTTPException(status_code=404, detail="Brief version not found")
    return result
