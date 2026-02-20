import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.database import Base, get_db
from src.shared.models import AuditMixin
from src.matter.models import Matter
from src.auth.models import User, Tenant, Group, Permission
from src.artifacts.models import ClaimGraphVersion, BriefVersion, SpecVersion
from src.workstreams.models import Workstream
from src.clients.models import Client
from src.documents.models import Document, DocumentChunk
from src.config import settings

engine = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI), echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

from sqlalchemy import select

async def seed_data():
    async with AsyncSessionLocal() as session:
        # Get an existing user
        result = await session.execute(select(User).limit(1))
        user = result.scalars().first()
        if not user:
            print("No user found in the DB. Please sign up a user first.")
            return
            
        tenant_id = user.tenant_id
        user_id = user.id

        # Create Client
        client_id = uuid.uuid4()
        client = Client(
            id=client_id,
            tenant_id=tenant_id,
            name="Acme Corp",
            company="Acme Corporation Ltd.",
            email="contact@acme.corp",
            phone="1-800-555-0199"
        )
        session.add(client)

        # Create Matter 1
        matter1 = Matter(
            id=uuid.UUID('123e4567-e89b-12d3-a456-426614174000'), # The DEMO_MATTER_ID used in MatterWorkspace
            tenant_id=tenant_id,
            attorney_id=user_id,
            client_id=client_id,
            title="Adaptive Sensor Fusion for Autonomous Vehicles",
            description="A novel method for fusing lidar and radar data in real-time.",
            status="CREATED",
            inventors=["Dr. Jane Smith", "John Doe"],
            assignee="Acme Corp",
            tech_domain="Autonomous Vehicles",
            defensibility_score=85
        )
        session.add(matter1)

        # Create Matter 2
        matter2 = Matter(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            attorney_id=user_id,
            client_id=client_id,
            title="Quantum Error Correction Algorithm",
            description="Improving coherence times in supraconducting qubits.",
            status="BRIEF_ANALYZED",
            inventors=["Dr. Alan Turing", "Grace Hopper"],
            assignee="Acme Corp",
            tech_domain="Quantum Computing",
            defensibility_score=92
        )
        session.add(matter2)
        
        await session.commit()
        print("Data seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
