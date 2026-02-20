from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.core.websockets.manager import manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    """
    WebSocket endpoint for real-time updates.
    room_id can be a business_id or store_id.
    """
    logger.info(f"🚀 WebSocket attempt for room: {room_id}")
    await manager.connect(websocket, room_id)
    try:
        while True:
            # Keep connection alive and listen for any client messages
            data = await websocket.receive_text()
            logger.debug(f"📥 Received from {room_id}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        logger.info(f"🔌 Client disconnected from room: {room_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket error in room {room_id}: {type(e).__name__}: {e}")
        manager.disconnect(websocket, room_id)
