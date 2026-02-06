"""
AKASHI MAM - Test Configuration
Pytest fixtures and configuration for all tests.
"""

import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Set testing environment
os.environ["TESTING"] = "true"
os.environ["ENVIRONMENT"] = "test"

from app.main import app
from app.core.database import get_db
from app.models.base import Base


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

# Use development database for now (create akashi_test database for production tests)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://akashi:akashi_dev_2025@localhost:5433/akashi_mam"
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    # Use existing tables (don't recreate - they already exist with partitions)
    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


# =============================================================================
# HTTP CLIENT FIXTURES
# =============================================================================

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create HTTP client for testing API endpoints."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_asset_data():
    """Sample asset data for testing."""
    return {
        "title": "Test Video",
        "asset_type": "video",
        "original_filename": "test_video.mp4",
        "tenant_code": "dev",
    }


@pytest.fixture
def sample_video_file(tmp_path):
    """Create a sample video file for upload testing."""
    video_file = tmp_path / "test_video.mp4"
    # Create a minimal valid file (not a real video, just for upload testing)
    video_file.write_bytes(b"fake video content for testing")
    return video_file


# =============================================================================
# MOCKS
# =============================================================================

@pytest.fixture
def mock_storage(mocker):
    """Mock storage service for testing without MinIO."""
    mock = mocker.patch("app.services.storage.StorageService")
    mock.return_value.upload_file.return_value = "test/path/file.mp4"
    mock.return_value.get_presigned_url.return_value = "https://minio.test/file.mp4"
    return mock
