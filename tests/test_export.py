import csv
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.export_service import ExportService, EXPORT_CSV_COLUMNS


def _make_mock_lead(**kwargs):
    """Create a mock lead with default values."""
    defaults = {
        "ig_username": "testuser",
        "ig_full_name": "Test User",
        "ig_bio_clean": "Marketing expert",
        "ig_website": "https://test.com",
        "ig_category": "Marketing Agency",
        "ig_follower_count": 5000,
        "score": 85,
        "score_reason": "Strong business profile",
        "lead_category": "agency",
        "research_summary": "Test research summary",
        "dm_message": "Hey Test, great profile!",
        "dm_variant_b": "Hi Test, love your work!",
    }
    defaults.update(kwargs)
    lead = MagicMock()
    for key, value in defaults.items():
        setattr(lead, key, value)
    return lead


class TestExportService:
    @pytest.fixture
    def export_service(self):
        return ExportService()

    @pytest.mark.asyncio
    async def test_export_csv_returns_valid_csv(self, export_service):
        mock_leads = [
            _make_mock_lead(ig_username="user1", score=90),
            _make_mock_lead(ig_username="user2", score=75),
        ]

        with patch.object(export_service, "_get_dm_ready_leads", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_leads
            result = await export_service.export_csv("campaign-123", AsyncMock())

        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["ig_username"] == "user1"
        assert rows[1]["ig_username"] == "user2"

    @pytest.mark.asyncio
    async def test_export_csv_has_correct_columns(self, export_service):
        mock_leads = [_make_mock_lead()]

        with patch.object(export_service, "_get_dm_ready_leads", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_leads
            result = await export_service.export_csv("campaign-123", AsyncMock())

        reader = csv.DictReader(io.StringIO(result))
        assert reader.fieldnames == EXPORT_CSV_COLUMNS

    @pytest.mark.asyncio
    async def test_export_csv_empty_campaign(self, export_service):
        with patch.object(export_service, "_get_dm_ready_leads", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            result = await export_service.export_csv("campaign-123", AsyncMock())

        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_export_csv_handles_none_fields(self, export_service):
        mock_lead = _make_mock_lead(
            ig_full_name=None,
            ig_website=None,
            ig_category=None,
            ig_bio_clean=None,
        )

        with patch.object(export_service, "_get_dm_ready_leads", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [mock_lead]
            result = await export_service.export_csv("campaign-123", AsyncMock())

        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["ig_full_name"] == ""
        assert rows[0]["ig_website"] == ""

    @pytest.mark.asyncio
    async def test_export_json_returns_list(self, export_service):
        mock_leads = [
            _make_mock_lead(ig_username="user1"),
            _make_mock_lead(ig_username="user2"),
        ]

        with patch.object(export_service, "_get_dm_ready_leads", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_leads
            result = await export_service.export_json("campaign-123", AsyncMock())

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["ig_username"] == "user1"

    @pytest.mark.asyncio
    async def test_export_json_includes_extra_fields(self, export_service):
        mock_lead = _make_mock_lead(
            score_reason="Great lead",
            research_summary="Found online presence",
            dm_variant_b="Alternative DM text",
        )

        with patch.object(export_service, "_get_dm_ready_leads", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [mock_lead]
            result = await export_service.export_json("campaign-123", AsyncMock())

        assert result[0]["score_reason"] == "Great lead"
        assert result[0]["research_summary"] == "Found online presence"
        assert result[0]["dm_variant_b"] == "Alternative DM text"

    @pytest.mark.asyncio
    async def test_export_json_empty_campaign(self, export_service):
        with patch.object(export_service, "_get_dm_ready_leads", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            result = await export_service.export_json("campaign-123", AsyncMock())

        assert result == []
