import asyncio
import sys
import os

# Ensure backend root is in python path
sys.path.append(os.getcwd())

from src.database import AsyncSessionLocal
from src.auth.models import User, Tenant, Group, Permission
# Import all models so SQLAlchemy can resolve all forward references
from src.matter.models import Matter
from src.artifacts.briefs.models import BriefVersion
from src.artifacts.specs.models import SpecVersion
from src.artifacts.claims.models import ClaimGraphVersion
from src.workstreams.models import Workstream
from src.auth.security import get_password_hash
from sqlalchemy import select

async def create_test_user():
    async with AsyncSessionLocal() as session:
        # 1. Create Tenant
        result = await session.execute(select(Tenant).where(Tenant.name == "Certis AI"))
        tenant = result.scalars().first()
        if not tenant:
            tenant = Tenant(name="Certis AI", domain="certis.ai")
            session.add(tenant)
            await session.flush()
            print(f"Created Tenant: {tenant.name}")
        else:
            print(f"Tenant exists: {tenant.name}")

        # 2. Create Permissions
        perms = ["matter:create", "matter:read", "matter:update", "user:read"]
        db_perms = []
        for codename in perms:
            result = await session.execute(select(Permission).where(Permission.codename == codename))
            perm = result.scalars().first()
            if not perm:
                perm = Permission(codename=codename, description=f"Permission to {codename}")
                session.add(perm)
                await session.flush()
                print(f"Created Permission: {perm.codename}")
            db_perms.append(perm)

        # 3. Create Group (Admin)
        result = await session.execute(select(Group).where(Group.name == "Admins"))
        group = result.scalars().first()
        if not group:
            group = Group(name="Admins", tenant_id=tenant.id)
            session.add(group)
            await session.flush()
            print(f"Created Group: {group.name}")
        
        # Assign permissions to group
        await session.refresh(group, attribute_names=["permissions"])
        for perm in db_perms:
            if perm not in group.permissions:
                group.permissions.append(perm)
        print("Assigned permissions to group")

        # 4. Create User
        email = "admin@certis.ai"
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if not user:
            hashed_pw = get_password_hash("password123")
            user = User(
                email=email,
                hashed_password=hashed_pw,
                full_name="Admin User",
                tenant_id=tenant.id,
                is_active=True
            )
            session.add(user)
            await session.flush()
            print(f"Created User: {user.email}")
        else:
            # Update password just in case
            user.hashed_password = get_password_hash("password123")
            print(f"Updated User password: {user.email}")

        # Assign user to group
        await session.refresh(user, attribute_names=["groups"])
        if group not in user.groups:
            user.groups.append(group)
            print(f"Added user to {group.name} group")

        await session.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(create_test_user())
