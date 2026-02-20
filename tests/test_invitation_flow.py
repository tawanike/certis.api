import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from src.main import app
from src.auth import models, security

@pytest.mark.asyncio
async def test_invitation_flow(db_session: AsyncSession):
    # 1. Setup: Create an admin/inviter user
    import uuid
    random_suffix = uuid.uuid4().hex[:8]
    inviter_email = f"inviter-{random_suffix}@example.com"
    inviter_password = "password123"
    hashed_password = security.get_password_hash(inviter_password)
    
    import uuid
    domain = f"test-{uuid.uuid4().hex[:8]}.com"
    tenant = models.Tenant(name="Test Tenant", domain=domain)
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    inviter = models.User(
        email=inviter_email,
        hashed_password=hashed_password,
        full_name="Inviter",
        tenant_id=tenant.id
    )
    db_session.add(inviter)
    await db_session.commit()
    await db_session.refresh(inviter)

    # Login to get token
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login_res = await ac.post("/v1/auth/login", json={
            "email": inviter_email,
            "password": inviter_password
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create Invitation
        invite_email = f"newuser-{uuid.uuid4().hex[:8]}@example.com"
        invite_res = await ac.post("/v1/auth/invitations", json={
            "email": invite_email
        }, headers=headers)
        assert invite_res.status_code == 200
        invite_data = invite_res.json()
        code = invite_data["code"]
        assert invite_data["email"] == invite_email

        # 3. Validate Invitation (Public)
        validate_res = await ac.get(f"/v1/auth/invitations/{code}")
        assert validate_res.status_code == 200
        assert validate_res.json()["status"] == "PENDING"

        # 4. Register with Invitation
        register_res = await ac.post("/v1/auth/register", json={
            "invite_code": code,
            "password": "newpassword123",
            "full_name": "New User"
        })
        assert register_res.status_code == 200
        assert "access_token" in register_res.json()

        # 5. Verify User Created and Invitation Accepted
        # Check DB or try to login
        login_new_res = await ac.post("/v1/auth/login", json={
            "email": invite_email,
            "password": "newpassword123"
        })
        assert login_new_res.status_code == 200

        # Verify old code cannot be used again
        register_res_2 = await ac.post("/v1/auth/register", json={
            "invite_code": code,
            "password": "anotherpassword",
            "full_name": "Another User"
        })
        assert register_res_2.status_code == 400
