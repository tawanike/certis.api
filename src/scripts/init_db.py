import asyncio
from src.database import engine, Base

# Import all models to ensure they are registered in Base.metadata
from src.shared.models import AuditMixin
from src.auth.models import Tenant, User
from src.matter.models import Matter
# src.chat.models does not exist yet (in-memory)
from src.drafting.models import ClaimGraphVersion

async def init_models():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Optional: Reset DB
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created.")

if __name__ == "__main__":
    asyncio.run(init_models())
