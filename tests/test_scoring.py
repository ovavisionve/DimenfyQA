import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scoring_service import BATCH_SIZE, ScoringService


@pytest.fixture
def scoring_service():
    with patch("app.services.scoring_service.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        service = ScoringService()
        return service


def _make_lead(
    ig_username="testbusiness",
    ig_full_name="Test Business Account",
    ig_bio="We help businesses grow | Marketing Agency | DM for collabs",
    ig_website="https://testbusiness.com",
    ig_category="Marketing Agency",
    ig_follower_count=15000,
    ig_following_count=800,
    ig_is_private=False,
    status="scraped",
):
    """Create a mock Lead ORM object."""
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.ig_username = ig_username
    lead.ig_full_name = ig_full_name
    lead.ig_bio = ig_bio
    lead.ig_bio_clean = None
    lead.ig_website = ig_website
    lead.ig_category = ig_category
    lead.ig_follower_count = ig_follower_count
    lead.ig_following_count = ig_following_count
    lead.ig_is_private = ig_is_private
    lead.status = status
    lead.score = None
    lead.score_reason = None
    lead.lead_category = None
    lead.scored_at = None
    return lead


def _make_mock_db(leads):
    """Create a mock async DB session that returns the given leads from execute()."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = leads
    mock_result.scalars.return_value = mock_scalars
    db.execute.return_value = mock_result
    return db


class TestScoreBatch:
    """Tests for the synchronous score_batch method (single API call)."""

    def test_score_batch_returns_list(self, scoring_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps([
                    {
                        "username": "testbusiness",
                        "score": 82,
                        "reason": "Active marketing agency with good follower count.",
                        "category": "agency",
                        "bio_clean": "We help businesses grow. Marketing Agency. DM for collabs",
                    }
                ])
            )
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            results = scoring_service.score_batch([sample_lead_data])

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["score"] == 82
        assert results[0]["category"] == "agency"
        assert results[0]["username"] == "testbusiness"
        assert "reason" in results[0]
        assert "bio_clean" in results[0]

    def test_score_batch_multiple_leads(self, scoring_service, sample_lead_data, sample_low_score_lead_data):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps([
                    {
                        "username": "testbusiness",
                        "score": 82,
                        "reason": "Marketing agency with solid presence.",
                        "category": "agency",
                        "bio_clean": "We help businesses grow",
                    },
                    {
                        "username": "randomuser123",
                        "score": 8,
                        "reason": "Personal account, private, no business indicators.",
                        "category": "other",
                        "bio_clean": "Just living life",
                    },
                ])
            )
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            results = scoring_service.score_batch([sample_lead_data, sample_low_score_lead_data])

        assert len(results) == 2
        assert results[0]["score"] == 82
        assert results[1]["score"] == 8

    def test_score_batch_strips_markdown_fences(self, scoring_service, sample_lead_data):
        json_body = json.dumps([
            {
                "username": "testbusiness",
                "score": 65,
                "reason": "test",
                "category": "coach",
                "bio_clean": "test",
            }
        ])
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=f"```json\n{json_body}\n```")
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            results = scoring_service.score_batch([sample_lead_data])

        assert len(results) == 1
        assert results[0]["score"] == 65

    def test_score_batch_raises_on_non_array(self, scoring_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({"score": 50, "reason": "test", "category": "other", "bio_clean": "test"})
            )
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            with pytest.raises(ValueError, match="Expected JSON array"):
                scoring_service.score_batch([sample_lead_data])

    def test_score_batch_raises_on_invalid_json(self, scoring_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json")]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            with pytest.raises(json.JSONDecodeError):
                scoring_service.score_batch([sample_lead_data])


class TestScoreBatchSafe:
    """Tests for _score_batch_safe which wraps score_batch with error handling."""

    def test_returns_results_mapped_by_username(self, scoring_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps([
                    {
                        "username": "testbusiness",
                        "score": 75,
                        "reason": "Good lead",
                        "category": "agency",
                        "bio_clean": "clean bio",
                    }
                ])
            )
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            results = scoring_service._score_batch_safe([sample_lead_data])

        assert len(results) == 1
        username, score_result = results[0]
        assert username == "testbusiness"
        assert score_result["score"] == 75

    def test_returns_none_for_missing_username_in_response(self, scoring_service):
        leads = [
            {"ig_username": "user_a", "ig_full_name": "A"},
            {"ig_username": "user_b", "ig_full_name": "B"},
        ]
        mock_response = MagicMock()
        # API only returns result for user_a, not user_b
        mock_response.content = [
            MagicMock(
                text=json.dumps([
                    {"username": "user_a", "score": 60, "reason": "ok", "category": "coach", "bio_clean": "a"},
                ])
            )
        ]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            results = scoring_service._score_batch_safe(leads)

        assert len(results) == 2
        assert results[0] == ("user_a", {"username": "user_a", "score": 60, "reason": "ok", "category": "coach", "bio_clean": "a"})
        assert results[1] == ("user_b", None)

    def test_returns_none_on_json_decode_error(self, scoring_service, sample_lead_data):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="NOT JSON")]

        with patch.object(
            scoring_service.client.messages, "create", return_value=mock_response
        ):
            results = scoring_service._score_batch_safe([sample_lead_data])

        assert len(results) == 1
        assert results[0] == ("testbusiness", None)

    def test_returns_none_on_api_exception(self, scoring_service, sample_lead_data):
        with patch.object(
            scoring_service.client.messages, "create", side_effect=Exception("API error")
        ):
            results = scoring_service._score_batch_safe([sample_lead_data])

        assert len(results) == 1
        assert results[0] == ("testbusiness", None)


class TestScoreLeadsBatch:
    """Tests for the async score_leads_batch method (full DB integration with mocks)."""

    @pytest.mark.asyncio
    async def test_scores_leads_and_updates_db(self, scoring_service):
        lead = _make_lead(ig_username="bizaccount", ig_follower_count=5000)
        lead_id = str(lead.id)
        db = _make_mock_db([lead])

        api_response = [
            {
                "username": "bizaccount",
                "score": 78,
                "reason": "Strong business profile",
                "category": "agency",
                "bio_clean": "We help businesses grow Marketing Agency DM for collabs",
            }
        ]
        with patch.object(scoring_service, "score_batch", return_value=api_response):
            scored_ids = await scoring_service.score_leads_batch([lead_id], db)

        assert len(scored_ids) == 1
        assert scored_ids[0] == lead_id
        assert lead.score == 78
        assert lead.score_reason == "Strong business profile"
        assert lead.lead_category == "agency"
        assert lead.status == "scored"
        assert lead.scored_at is not None
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_scores_zero_for_empty_profiles(self, scoring_service):
        """Leads with no bio, no followers, no name should get score 0 without API call."""
        lead = _make_lead(
            ig_username="emptyuser",
            ig_full_name=None,
            ig_bio=None,
            ig_follower_count=0,
            ig_website=None,
            ig_category=None,
        )
        lead_id = str(lead.id)
        db = _make_mock_db([lead])

        with patch.object(scoring_service, "score_batch") as mock_score:
            scored_ids = await scoring_service.score_leads_batch([lead_id], db)

        # score_batch should NOT be called for empty profiles
        mock_score.assert_not_called()

        assert lead.score == 0
        assert lead.status == "scored"
        assert "No profile data" in lead.score_reason
        assert lead.lead_category == "other"
        assert lead.scored_at is not None
        # Auto-scored leads don't go through the batch path so not in scored_ids
        assert len(scored_ids) == 0

    @pytest.mark.asyncio
    async def test_auto_scores_zero_for_whitespace_only_profiles(self, scoring_service):
        """Leads with whitespace-only bio and name should also be auto-scored 0."""
        lead = _make_lead(
            ig_username="blanky",
            ig_full_name="   ",
            ig_bio="  ",
            ig_follower_count=0,
        )
        lead_id = str(lead.id)
        db = _make_mock_db([lead])

        with patch.object(scoring_service, "score_batch") as mock_score:
            await scoring_service.score_leads_batch([lead_id], db)

        mock_score.assert_not_called()
        assert lead.score == 0
        assert lead.status == "scored"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_scraped_leads(self, scoring_service):
        db = _make_mock_db([])

        scored_ids = await scoring_service.score_leads_batch(["fake-id"], db)
        assert scored_ids == []

    @pytest.mark.asyncio
    async def test_mixed_empty_and_real_leads(self, scoring_service):
        """A mix of empty and real leads: empty ones auto-score, real ones go to API."""
        empty_lead = _make_lead(
            ig_username="emptyuser",
            ig_full_name=None,
            ig_bio=None,
            ig_follower_count=0,
            ig_website=None,
            ig_category=None,
        )
        real_lead = _make_lead(ig_username="realuser", ig_follower_count=10000)
        db = _make_mock_db([empty_lead, real_lead])

        api_response = [
            {
                "username": "realuser",
                "score": 85,
                "reason": "Great lead",
                "category": "ecommerce",
                "bio_clean": "clean",
            }
        ]
        with patch.object(scoring_service, "score_batch", return_value=api_response):
            scored_ids = await scoring_service.score_leads_batch(
                [str(empty_lead.id), str(real_lead.id)], db
            )

        # Only real_lead comes back as scored_id (empty_lead is auto-scored but not in scored_ids)
        assert len(scored_ids) == 1
        assert empty_lead.score == 0
        assert empty_lead.status == "scored"
        assert real_lead.score == 85
        assert real_lead.status == "scored"

    @pytest.mark.asyncio
    async def test_progress_callback_is_called(self, scoring_service):
        lead = _make_lead(ig_username="proguser", ig_follower_count=3000)
        lead_id = str(lead.id)
        db = _make_mock_db([lead])

        callback = MagicMock()

        api_response = [
            {"username": "proguser", "score": 50, "reason": "ok", "category": "other", "bio_clean": "bio"}
        ]
        with patch.object(scoring_service, "score_batch", return_value=api_response):
            await scoring_service.score_leads_batch([lead_id], db, progress_callback=callback)

        callback.assert_called_once_with(1, 1, "proguser")

    @pytest.mark.asyncio
    async def test_handles_api_failure_gracefully(self, scoring_service):
        """If the API call fails, the lead should not be updated (score stays None)."""
        lead = _make_lead(ig_username="failuser", ig_follower_count=2000)
        lead_id = str(lead.id)
        db = _make_mock_db([lead])

        with patch.object(
            scoring_service, "score_batch", side_effect=Exception("API down")
        ):
            scored_ids = await scoring_service.score_leads_batch([lead_id], db)

        # _score_batch_safe catches the exception, returns None for the lead
        assert len(scored_ids) == 0
        assert lead.score is None
        assert lead.status == "scraped"  # unchanged

    @pytest.mark.asyncio
    async def test_valid_categories_in_response(self, scoring_service):
        """Verify that category values from the API are stored as-is."""
        valid_categories = ["coach", "ecommerce", "saas", "agency", "creator", "local_business", "other"]

        for category in valid_categories:
            lead = _make_lead(ig_username=f"user_{category}", ig_follower_count=1000)
            lead_id = str(lead.id)
            db = _make_mock_db([lead])

            api_response = [
                {"username": f"user_{category}", "score": 50, "reason": "test", "category": category, "bio_clean": "test"}
            ]
            with patch.object(scoring_service, "score_batch", return_value=api_response):
                await scoring_service.score_leads_batch([lead_id], db)

            assert lead.lead_category == category
