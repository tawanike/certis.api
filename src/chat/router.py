from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import require_tenant_matter
from src.chat.schemas import ChatRequest, ChatResponse
from src.chat.service import ChatService
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/matters", tags=["chat"])


@router.post("/{matter_id}/chat", response_model=ChatResponse)
async def chat_with_matter(
    matter_id: UUID,
    request: ChatRequest,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = ChatService(db=db)
    result = await service.chat(matter_id, request.message)
    return result


@router.post("/{matter_id}/stream")
async def chat_stream(
    matter_id: UUID,
    request: ChatRequest,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = ChatService(db=db)
    return EventSourceResponse(service.stream_chat(matter_id, request.message))
