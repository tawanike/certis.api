import pytest
from httpx import AsyncClient
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.auth.models import User, Group, Permission, group_permissions, user_groups, Tenant
from src.auth.security import get_password_hash

# Helper to create a user with specific permissions for testing
async def create_user_with_permissions(db: AsyncSession, email: str, perms: list[str]) -> User:
    # 0. Create a tenant
    tenant_id = uuid4()
    tenant = Tenant(id=tenant_id, name=f"TestTenant_{uuid4()}")
    db.add(tenant)
    await db.flush()

    # 1. Create permissions if they don't exist
    for p_name in perms:
        perm = await db.execute(text("SELECT * FROM permissions WHERE codename = :c"), {"c": p_name})
        if not perm.first():
            new_perm = Permission(id=uuid4(), codename=p_name, description=f"Test {p_name}")
            db.add(new_perm)
    
    # 2. Create a test group
    group_id = uuid4()
    group = Group(id=group_id, name=f"TestGroup_{uuid4()}", tenant_id=tenant_id)
    db.add(group)
    await db.flush()

    # 3. Associate permissions with group
    for p_name in perms:
        p_res = await db.execute(text("SELECT id FROM permissions WHERE codename = :c"), {"c": p_name})
        p_id = p_res.scalar_one()
        await db.execute(group_permissions.insert().values(group_id=group_id, permission_id=p_id))

    # 4. Create user
    user_id = uuid4()
    user = User(
        id=user_id,
        email=email,
        hashed_password=get_password_hash("password123"),
        is_active=True,
        tenant_id=group.tenant_id
    )
    db.add(user)
    await db.flush()

    # 5. Assign user to group
    await db.execute(user_groups.insert().values(user_id=user_id, group_id=group_id))
    await db.commit()
    return user

@pytest.mark.asyncio
async def test_rbac_access_granted(async_client: AsyncClient, db_session: AsyncSession):
    # Create an admin user with specific fake permission
    email = f"admin_{uuid4()}@test.ai"
    await create_user_with_permissions(db_session, email, ["test:write"])

    # Login to get token
    login_response = await async_client.post("/v1/auth/login", json={"email": email, "password": "password123"})
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Hit the test protected endpoint
    response = await async_client.get("/v1/auth/test-permission/write", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "You have testing write access"

@pytest.mark.asyncio
async def test_rbac_access_denied(async_client: AsyncClient, db_session: AsyncSession):
    # Create a basic user WITHOUT the required permission
    email = f"user_{uuid4()}@test.ai"
    await create_user_with_permissions(db_session, email, ["test:read"]) # Missing test:write

    # Login to get token
    login_response = await async_client.post("/v1/auth/login", json={"email": email, "password": "password123"})
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Hit the test protected endpoint which requires test:write
    response = await async_client.get("/v1/auth/test-permission/write", headers=headers)
    assert response.status_code == 403
    assert "Missing permission" in response.json()["detail"]
