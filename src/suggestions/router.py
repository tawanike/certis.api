from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import require_tenant_matter
from src.suggestions.schemas import SuggestionsResponse
from src.suggestions.service import SuggestionsService

router = APIRouter(prefix="/matters", tags=["suggestions"])


@router.get("/{matter_id}/suggestions", response_model=SuggestionsResponse)
async def get_suggestions(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = SuggestionsService(db)
    context = await service._build_context(matter_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Matter not found")

    suggestions = await service.generate_suggestions(matter_id)
    return SuggestionsResponse(
        suggestions=suggestions,
        matter_status=context["status"],
    )
