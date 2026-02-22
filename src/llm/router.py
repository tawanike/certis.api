from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import models
from src.auth.dependencies import get_current_active_user
from src.database import get_db
from src.llm.schemas import LLMSettingsResponse, LLMSettingsUpdate
from src.llm.service import LLMSettingsService

router = APIRouter(prefix="/settings/llm", tags=["settings"])


@router.get("", response_model=LLMSettingsResponse)
async def get_llm_settings(
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = LLMSettingsService(db)
    return await service.get_effective_settings(current_user.tenant_id)


@router.patch("", response_model=LLMSettingsResponse)
async def update_llm_settings(
    update: LLMSettingsUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = LLMSettingsService(db)
    return await service.update_settings(current_user.tenant_id, update)
