from typing import List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from src.clients.models import Client
from src.clients.schemas import ClientCreate, ClientUpdate

class ClientService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_client(self, client_in: ClientCreate, tenant_id: UUID) -> Client:
        db_client = Client(
            **client_in.model_dump(),
            tenant_id=tenant_id
        )
        self.db.add(db_client)
        await self.db.commit()
        await self.db.refresh(db_client)
        return db_client

    async def list_clients(self, tenant_id: UUID, skip: int = 0, limit: int = 100) -> List[Client]:
        query = select(Client).where(Client.tenant_id == tenant_id).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_client(self, client_id: UUID, tenant_id: UUID) -> Client:
        query = select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id)
        result = await self.db.execute(query)
        client = result.scalar_one_or_none()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return client

    async def update_client(self, client_id: UUID, tenant_id: UUID, client_in: ClientUpdate) -> Client:
        client = await self.get_client(client_id, tenant_id)
        
        update_data = client_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(client, field, value)
            
        await self.db.commit()
        await self.db.refresh(client)
        return client
