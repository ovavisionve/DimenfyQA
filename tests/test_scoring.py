import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.scoring_service import ScoringService


@pytest.fixture
def scoring_service():
    with patch("app.services.scoring_service.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        service = ScoringService()
        return service


class TestScoringService:
    def test_score_lead_high_score(self, scoring_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({
                    "score": 82,
                    "reason": "Active marketing agency with good follower count and business bio.",
                    "category": "agency",
                    "bio_clean": "We help businesses grow. Marketing Agency. DM for collabs",
                })
            )
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            result = scoring_service.score_lead(sample_lead_data)

        assert result["score"] == 82
        assert result["category"] == "agency"
        assert "reason" in result
        assert "bio_clean" in result

    def test_score_lead_low_score(self, scoring_service, sample_low_score_lead_data):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({
                    "score": 8,
                    "reason": "Personal account with very few followers, private, no business indicators.",
                    "category": "other",
                    "bio_clean": "Just living life",
                })
            )
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            result = scoring_service.score_lead(sample_low_score_lead_data)

        assert result["score"] == 8
        assert result["category"] == "other"

    def test_score_lead_returns_valid_json(self, scoring_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"score": 65, "reason": "test", "category": "coach", "bio_clean": "test"}'
            )
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            result = scoring_service.score_lead(sample_lead_data)

        assert isinstance(result, dict)
        assert "score" in result
        assert 0 <= result["score"] <= 100
        assert result["category"] in (
            "coach", "ecommerce", "saas", "agency", "creator", "local_business", "other"
        )
