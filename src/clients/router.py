from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.clients.schemas import ClientCreate, ClientUpdate, ClientResponse
from src.clients.service import ClientService

router = APIRouter(prefix="/clients", tags=["clients"])

# Dummy IDs for MVP until Auth is implemented
DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")

@router.post("", response_model=ClientResponse)
async def create_client(client: ClientCreate, db: AsyncSession = Depends(get_db)):
    service = ClientService(db)
    return await service.create_client(client, DEMO_TENANT_ID)

@router.get("", response_model=List[ClientResponse])
async def list_clients(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    service = ClientService(db)
    return await service.list_clients(DEMO_TENANT_ID, skip, limit)

@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(client_id: UUID, db: AsyncSession = Depends(get_db)):
    service = ClientService(db)
    return await service.get_client(client_id, DEMO_TENANT_ID)

@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(client_id: UUID, client: ClientUpdate, db: AsyncSession = Depends(get_db)):
    service = ClientService(db)
    return await service.update_client(client_id, DEMO_TENANT_ID, client)
