from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.research_service import ResearchService


@pytest.fixture
def research_service():
    with patch("app.services.research_service.settings") as mock_settings:
        mock_settings.PERPLEXITY_API_KEY = "test-key"
        mock_settings.RESEARCH_SCORE_THRESHOLD = 60
        service = ResearchService()
        return service


class TestResearchService:
    @pytest.mark.asyncio
    async def test_research_lead_returns_text(self, research_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Test Business is a Miami-based marketing agency focused on growth."}}
            ]
        }

        with patch("app.services.research_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await research_service.research_lead(sample_lead_data)

        assert isinstance(result, str)
        assert "marketing agency" in result.lower()

    @pytest.mark.asyncio
    async def test_research_lead_sends_correct_prompt(self, research_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Research result"}}]
        }

        with patch("app.services.research_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await research_service.research_lead(sample_lead_data)

            # Verify the API call was made with correct structure
            call_kwargs = mock_client.post.call_args
            assert "api.perplexity.ai" in str(call_kwargs)
            json_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert json_body["model"] == "sonar"
            assert len(json_body["messages"]) == 1

    @pytest.mark.asyncio
    async def test_research_lead_uses_clean_bio_when_available(self, research_service):
        lead_data = {
            "ig_username": "testuser",
            "ig_full_name": "Test User",
            "ig_bio": "Raw bio with 🚀 emojis",
            "ig_bio_clean": "Clean bio without emojis",
            "ig_website": "https://test.com",
            "lead_category": "coach",
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Research result"}}]
        }

        with patch("app.services.research_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await research_service.research_lead(lead_data)

            call_kwargs = mock_client.post.call_args
            json_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            prompt_content = json_body["messages"][0]["content"]
            # Should use clean bio, not raw bio
            assert "Clean bio without emojis" in prompt_content
