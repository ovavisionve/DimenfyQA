import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app


def _make_mock_client(**kwargs):
    """Create a mock Client object."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Agency",
        "business_type": "B2B automation",
        "ig_accounts": ["@testagency"],
        "settings": {"service_description": "We help with automation"},
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    client = MagicMock()
    for key, value in defaults.items():
        setattr(client, key, value)
    return client


@pytest_asyncio.fixture
async def client():
    """HTTP test client with mocked DB session."""
    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, mock_db
    app.dependency_overrides.clear()


class TestClientEndpoints:
    @pytest.mark.asyncio
    async def test_create_client_returns_201(self, client):
        ac, mock_db = client
        mock_client = _make_mock_client()

        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.api.endpoints.clients.Client", return_value=mock_client):
            response = await ac.post(
                "/api/v1/clients/",
                json={"name": "Test Agency", "business_type": "B2B automation"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Agency"

    @pytest.mark.asyncio
    async def test_create_client_missing_name_returns_422(self, client):
        ac, _ = client
        response = await ac.post("/api/v1/clients/", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_clients_returns_200(self, client):
        ac, mock_db = client
        mock_clients = [_make_mock_client(name="Agency 1"), _make_mock_client(name="Agency 2")]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_clients
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await ac.get("/api/v1/clients/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_client_not_found(self, client):
        ac, mock_db = client
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await ac.get(f"/api/v1/clients/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_client_found(self, client):
        ac, mock_db = client
        mock_client = _make_mock_client()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await ac.get(f"/api/v1/clients/{mock_client.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Agency"

    @pytest.mark.asyncio
    async def test_update_client_not_found(self, client):
        ac, mock_db = client
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await ac.patch(
            f"/api/v1/clients/{uuid.uuid4()}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_client_success(self, client):
        ac, mock_db = client
        mock_client = _make_mock_client()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        response = await ac.patch(
            f"/api/v1/clients/{mock_client.id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert mock_client.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_delete_client_not_found(self, client):
        ac, mock_db = client
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await ac.delete(f"/api/v1/clients/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_client_soft_deletes(self, client):
        ac, mock_db = client
        mock_client = _make_mock_client(is_active=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        response = await ac.delete(f"/api/v1/clients/{mock_client.id}")
        assert response.status_code == 204
        assert mock_client.is_active is False
