import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models.base import Base


# Use an in-memory SQLite for tests is not possible with asyncpg,
# so we use a test PostgreSQL database or skip DB-dependent tests.
# For unit tests, we mock the DB.


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_lead_data() -> dict:
    return {
        "ig_username": "testbusiness",
        "ig_full_name": "Test Business Account",
        "ig_bio": "We help businesses grow 🚀 | Marketing Agency | DM for collabs",
        "ig_website": "https://testbusiness.com",
        "ig_category": "Marketing Agency",
        "ig_follower_count": 15000,
        "ig_following_count": 800,
        "ig_is_private": False,
    }


@pytest.fixture
def sample_low_score_lead_data() -> dict:
    return {
        "ig_username": "randomuser123",
        "ig_full_name": "Random User",
        "ig_bio": "Just living life ✨",
        "ig_website": None,
        "ig_category": None,
        "ig_follower_count": 50,
        "ig_following_count": 200,
        "ig_is_private": True,
    }


@pytest.fixture
def sample_client_config() -> dict:
    return {
        "business_type": "B2B automation agency",
        "service_description": "We help businesses automate their lead generation using AI-powered Instagram DMs.",
    }
