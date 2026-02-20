from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db, AsyncSessionLocal
from src.chat.schemas import ChatRequest, ChatResponse
from src.chat.service import ChatService
import json
import logging
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matters", tags=["chat"])

@router.post("/{matter_id}/chat", response_model=ChatResponse)
async def chat_with_matter(matter_id: UUID, request: ChatRequest, db: AsyncSession = Depends(get_db)):
    service = ChatService(db=db)
    result = await service.chat(matter_id, request.message)
    return result

@router.post("/{matter_id}/stream")
async def chat_stream(matter_id: UUID, request: ChatRequest, db: AsyncSession = Depends(get_db)):
    service = ChatService(db=db)
    return EventSourceResponse(service.stream_chat(matter_id, request.message))
