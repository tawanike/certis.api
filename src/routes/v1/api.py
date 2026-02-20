from fastapi import APIRouter

from src.matter.router import router as matter_router
from src.chat.router import router as chat_router
from src.drafting.router import router as drafting_router
from src.briefing.router import router as briefing_router
from src.documents.router import router as documents_router
from src.clients.router import router as clients_router

api_router = APIRouter()


from src.routes.v1.websockets import router as ws_router

api_router.include_router(matter_router)
api_router.include_router(chat_router)
api_router.include_router(drafting_router)
api_router.include_router(briefing_router)
api_router.include_router(documents_router)
api_router.include_router(clients_router)
api_router.include_router(ws_router, prefix="/ws")
