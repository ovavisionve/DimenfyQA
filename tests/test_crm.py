"""Tests for the CRM service — Kanban pipeline with dynamic scoring."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.crm_service import CrmService, INTEREST_KEYWORDS, LOST_KEYWORDS


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
def _make_lead(
    ig_username="testlead",
    ig_full_name="Test Lead",
    ig_bio="Marketing guru | DMs open",
    score=75,
    status="sent",
    dm_message="Hey! Love your content.",
    reply_text=None,
    reply_classification=None,
    conversation_status="awaiting_reply",
    crm_stage="new",
    sent_at=None,
    replied_at=None,
    follow_up_count=0,
    ig_profile_pic_url=None,
    ig_follower_count=5000,
    ig_following_count=300,
    score_reason="Good engagement",
    lead_category="agency",
    research_summary=None,
    comment_message=None,
    comment_sent_at=None,
):
    """Create a mock Lead ORM object for CRM tests."""
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.campaign_id = uuid.uuid4()
    lead.client_id = uuid.uuid4()
    lead.ig_username = ig_username
    lead.ig_full_name = ig_full_name
    lead.ig_bio = ig_bio
    lead.ig_profile_pic_url = ig_profile_pic_url
    lead.ig_follower_count = ig_follower_count
    lead.ig_following_count = ig_following_count
    lead.score = score
    lead.score_reason = score_reason
    lead.lead_category = lead_category
    lead.research_summary = research_summary
    lead.status = status
    lead.dm_message = dm_message
    lead.reply_text = reply_text
    lead.reply_classification = reply_classification
    lead.conversation_status = conversation_status
    lead.crm_stage = crm_stage
    lead.sent_at = sent_at or datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
    lead.replied_at = replied_at
    lead.follow_up_count = follow_up_count
    lead.comment_message = comment_message
    lead.comment_sent_at = comment_sent_at
    return lead


# ------------------------------------------------------------------ #
# Tests: _lead_to_card
# ------------------------------------------------------------------ #
class TestLeadToCard:
    """Tests for converting a Lead ORM to CRM card dict."""

    def test_basic_card(self):
        service = CrmService()
        lead = _make_lead()
        card = service._lead_to_card(lead)

        assert card["ig_username"] == "testlead"
        assert card["ig_full_name"] == "Test Lead"
        assert card["score"] == 75
        assert card["crm_stage"] == "new"
        assert card["has_reply"] is False
        assert card["lead_id"] == str(lead.id)

    def test_card_with_reply(self):
        service = CrmService()
        lead = _make_lead(
            reply_text="Sounds interesting!",
            replied_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
        )
        card = service._lead_to_card(lead)

        assert card["has_reply"] is True
        assert "Sounds interesting" in card["last_message_preview"]
        assert card["last_message_at"] is not None

    def test_long_message_truncated(self):
        service = CrmService()
        lead = _make_lead(dm_message="A" * 200)
        card = service._lead_to_card(lead)

        assert len(card["last_message_preview"]) <= 83  # 80 + "..."
        assert card["last_message_preview"].endswith("...")


# ------------------------------------------------------------------ #
# Tests: auto_classify_stage
# ------------------------------------------------------------------ #
class TestAutoClassifyStage:
    """Tests for automatic CRM stage transitions based on events."""

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_lead(self):
        service = CrmService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.auto_classify_stage("nonexistent", db, event="dm_sent")
        assert result is None

    @pytest.mark.asyncio
    async def test_dm_sent_moves_new_to_contacted(self):
        service = CrmService()
        lead = _make_lead(crm_stage="new")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="dm_sent")
        assert result == "contacted"
        assert lead.crm_stage == "contacted"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_dm_sent_no_change_if_already_contacted(self):
        service = CrmService()
        lead = _make_lead(crm_stage="contacted")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="dm_sent")
        assert result is None

    @pytest.mark.asyncio
    async def test_reply_received_moves_contacted_to_replied(self):
        service = CrmService()
        lead = _make_lead(crm_stage="contacted", reply_text="Thanks for reaching out")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="reply_received")
        assert result == "replied"

    @pytest.mark.asyncio
    async def test_reply_with_interest_keyword_moves_to_interested(self):
        service = CrmService()
        lead = _make_lead(crm_stage="contacted", reply_text="¿Cuánto cuesta el servicio?")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="reply_received")
        assert result == "interested"
        assert lead.crm_stage == "interested"

    @pytest.mark.asyncio
    async def test_reply_with_lost_keyword_moves_to_closed_lost(self):
        service = CrmService()
        lead = _make_lead(crm_stage="contacted", reply_text="No gracias, no me interesa")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="reply_received")
        assert result == "closed_lost"
        assert lead.crm_stage == "closed_lost"

    @pytest.mark.asyncio
    async def test_reply_positive_moves_to_interested(self):
        service = CrmService()
        lead = _make_lead(crm_stage="replied")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="reply_positive")
        assert result == "interested"

    @pytest.mark.asyncio
    async def test_reply_positive_does_not_override_closed_won(self):
        service = CrmService()
        lead = _make_lead(crm_stage="closed_won")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="reply_positive")
        assert result is None

    @pytest.mark.asyncio
    async def test_reply_negative_moves_to_closed_lost(self):
        service = CrmService()
        lead = _make_lead(crm_stage="replied")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="reply_negative")
        assert result == "closed_lost"

    @pytest.mark.asyncio
    async def test_reply_negative_does_not_override_closed_won(self):
        service = CrmService()
        lead = _make_lead(crm_stage="closed_won")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_classify_stage(str(lead.id), db, event="reply_negative")
        assert result is None


# ------------------------------------------------------------------ #
# Tests: move_lead
# ------------------------------------------------------------------ #
class TestMoveLead:
    """Tests for manually moving leads between stages."""

    @pytest.mark.asyncio
    async def test_move_lead_success(self):
        service = CrmService()
        lead = _make_lead(crm_stage="contacted")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.move_lead(str(lead.id), "interested", db)
        assert result["success"] is True
        assert result["old_stage"] == "contacted"
        assert result["new_stage"] == "interested"
        assert lead.crm_stage == "interested"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_move_lead_not_found(self):
        service = CrmService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.move_lead("nonexistent", "interested", db)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_move_lead_invalid_stage(self):
        service = CrmService()
        lead = _make_lead()
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.move_lead(str(lead.id), "invalid_stage", db)
        assert "error" in result
        assert "Invalid stage" in result["error"]


# ------------------------------------------------------------------ #
# Tests: add_note
# ------------------------------------------------------------------ #
class TestAddNote:
    """Tests for adding notes to leads."""

    @pytest.mark.asyncio
    async def test_add_note_success(self):
        service = CrmService()
        lead = _make_lead()
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.add_note(str(lead.id), "Great prospect!", db, user_id="user-123")
        assert result is not None
        assert result["content"] == "Great prospect!"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_note_lead_not_found(self):
        service = CrmService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.add_note("nonexistent", "Note", db)
        assert result is None


# ------------------------------------------------------------------ #
# Tests: get_lead_detail
# ------------------------------------------------------------------ #
class TestGetLeadDetail:
    """Tests for retrieving full lead detail."""

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_lead(self):
        service = CrmService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.get_lead_detail("nonexistent", db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_full_detail(self):
        service = CrmService()
        lead = _make_lead(
            reply_text="Tell me more!",
            replied_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
            crm_stage="replied",
        )
        db = AsyncMock()
        db.get.return_value = lead

        # Mock execute calls: score_history, notes, conversation_messages
        empty_result = MagicMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result.scalars.return_value = empty_scalars

        db.execute.return_value = empty_result

        result = await service.get_lead_detail(str(lead.id), db)

        assert result is not None
        assert result["lead"]["ig_username"] == "testlead"
        assert result["lead"]["crm_stage"] == "replied"
        assert result["score_history"] == []
        assert result["notes"] == []
        # Should reconstruct messages from lead fields
        assert len(result["messages"]) == 2
        assert result["messages"][0]["direction"] == "outbound"
        assert result["messages"][1]["direction"] == "inbound"


# ------------------------------------------------------------------ #
# Tests: update_conversation_score
# ------------------------------------------------------------------ #
class TestUpdateConversationScore:
    """Tests for dynamic scoring via Claude."""

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_lead(self):
        service = CrmService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.update_conversation_score("nonexistent", db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_reply(self):
        service = CrmService()
        lead = _make_lead(reply_text=None)
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.update_conversation_score(str(lead.id), db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_score(self):
        service = CrmService()
        lead = _make_lead(score=None, reply_text="Hello")
        db = AsyncMock()
        db.get.return_value = lead

        result = await service.update_conversation_score(str(lead.id), db)
        assert result is None

    @pytest.mark.asyncio
    async def test_positive_delta_increases_score(self):
        service = CrmService()
        lead = _make_lead(score=70, reply_text="¿Cuánto cuesta?")
        db = AsyncMock()
        db.get.return_value = lead

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"delta": 15, "reason": "Asks about price"}')]

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = await service.update_conversation_score(str(lead.id), db)

        assert result is not None
        assert result["old_score"] == 70
        assert result["new_score"] == 85
        assert result["delta"] == 15
        assert lead.score == 85
        db.add.assert_called_once()  # ScoreHistory added
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_negative_delta_decreases_score(self):
        service = CrmService()
        lead = _make_lead(score=50, reply_text="No me interesa")
        db = AsyncMock()
        db.get.return_value = lead

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"delta": -20, "reason": "Clear rejection"}')]

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = await service.update_conversation_score(str(lead.id), db)

        assert result is not None
        assert result["old_score"] == 50
        assert result["new_score"] == 30
        assert result["delta"] == -20

    @pytest.mark.asyncio
    async def test_score_clamped_to_0_100(self):
        service = CrmService()
        lead = _make_lead(score=5, reply_text="Terrible, stop messaging me")
        db = AsyncMock()
        db.get.return_value = lead

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"delta": -20, "reason": "Very negative"}')]

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = await service.update_conversation_score(str(lead.id), db)

        assert result["new_score"] == 0  # Clamped, not -15

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        service = CrmService()
        lead = _make_lead(score=70, reply_text="Hello")
        db = AsyncMock()
        db.get.return_value = lead

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.side_effect = Exception("API Error")
            result = await service.update_conversation_score(str(lead.id), db)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_json_parse_error(self):
        service = CrmService()
        lead = _make_lead(score=70, reply_text="Hello")
        db = AsyncMock()
        db.get.return_value = lead

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json")]

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = await service.update_conversation_score(str(lead.id), db)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_markdown_wrapped_json(self):
        service = CrmService()
        lead = _make_lead(score=60, reply_text="Interesting")
        db = AsyncMock()
        db.get.return_value = lead

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='```json\n{"delta": 10, "reason": "Mild interest"}\n```')]

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = await service.update_conversation_score(str(lead.id), db)

        assert result is not None
        assert result["delta"] == 10
        assert result["new_score"] == 70

    @pytest.mark.asyncio
    async def test_delta_clamped_to_range(self):
        """Delta values outside -20 to +20 are clamped."""
        service = CrmService()
        lead = _make_lead(score=50, reply_text="I want to buy NOW")
        db = AsyncMock()
        db.get.return_value = lead

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"delta": 50, "reason": "Extreme intent"}')]

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = await service.update_conversation_score(str(lead.id), db)

        assert result["delta"] == 20  # Clamped to max


# ------------------------------------------------------------------ #
# Tests: get_score_history
# ------------------------------------------------------------------ #
class TestGetScoreHistory:
    """Tests for score change timeline."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        service = CrmService()
        db = AsyncMock()

        empty_result = MagicMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result.scalars.return_value = empty_scalars
        db.execute.return_value = empty_result

        result = await service.get_score_history("some-lead-id", db)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_history_entries(self):
        service = CrmService()
        db = AsyncMock()

        entry = MagicMock()
        entry.old_score = 70
        entry.new_score = 85
        entry.delta = 15
        entry.reason = "Price inquiry"
        entry.created_at = datetime(2026, 3, 21, 14, 0, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [entry]
        mock_result.scalars.return_value = mock_scalars
        db.execute.return_value = mock_result

        result = await service.get_score_history("some-lead-id", db)
        assert len(result) == 1
        assert result[0]["old_score"] == 70
        assert result[0]["new_score"] == 85
        assert result[0]["delta"] == 15
        assert result[0]["reason"] == "Price inquiry"
