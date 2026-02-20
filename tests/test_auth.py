import pytest
from httpx import AsyncClient

# Using the admin user created by the seed script
TEST_EMAIL = "admin@certis.ai"
TEST_PASSWORD = "password123"

@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient):
    response = await async_client.post(
        "/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_failure(async_client: AsyncClient):
    response = await async_client.post(
        "/v1/auth/login",
        json={"email": TEST_EMAIL, "password": "wrongpassword"}
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Incorrect email or password"
