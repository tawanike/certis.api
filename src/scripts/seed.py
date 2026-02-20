import asyncio
from uuid import UUID
from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.auth.models import Tenant, User
# Import ClaimGraphVersion to ensure it is registered for the 'Matter.claim_versions' relationship
from src.artifacts.models import ClaimGraphVersion

DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000002")

async def seed_data():
    async with AsyncSessionLocal() as session:
        # 1. Create Tenant
        tenant = await session.get(Tenant, DEMO_TENANT_ID)
        if not tenant:
            print("Creating Demo Tenant...")
            tenant = Tenant(
                id=DEMO_TENANT_ID,
                name="Demo Law Firm",
                domain="demo.law"
            )
            session.add(tenant)
        
        # 2. Create User
        user = await session.get(User, DEMO_USER_ID)
        if not user:
            print("Creating Demo User...")
            user = User(
                id=DEMO_USER_ID,
                email="attorney@demo.law",
                full_name="Alice Attorney",
                tenant_id=DEMO_TENANT_ID
            )
            session.add(user)
            
        await session.commit()
        print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed_data())
