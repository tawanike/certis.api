import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator, Generator
import asyncio
from src.main import app
from src.config import settings
from src.database import get_db, Base

# Use a test database URL if possible, or force a distinct one
# For this setup, we'll assume the main DB is safe or use an in-memory SQLite for speed/isolation if preferred
# But since we use Postgres specific features (pgvector/jsonb likely), we should stick to Postgres
# WARNING: This configuration runs against the configured database. 
# Ideal setup requires a separate test database.



@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    # Create a new engine for this loop
    test_engine = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI), echo=False)
    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    async with TestingSessionLocal() as session:
        yield session
    
    await test_engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Client for testing API endpoints."""
    # Override the get_db dependency to use our test session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()
