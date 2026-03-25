"""Tests for the Unibox service — unified inbox with AI reply suggestions."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.unibox_service import UniboxService


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
    dm_variant_b=None,
    dm_variant_used="A",
    reply_text=None,
    reply_classification=None,
    conversation_status="awaiting_reply",
    sent_at=None,
    replied_at=None,
    follow_up_count=0,
    ig_profile_pic_url=None,
    ig_follower_count=5000,
    ig_following_count=300,
    ig_is_private=False,
    score_reason="Good engagement",
    lead_category="agency",
    research_summary=None,
    comment_message=None,
    comment_sent_at=None,
):
    """Create a mock Lead ORM object for unibox tests."""
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
    lead.ig_is_private = ig_is_private
    lead.score = score
    lead.score_reason = score_reason
    lead.lead_category = lead_category
    lead.research_summary = research_summary
    lead.status = status
    lead.dm_message = dm_message
    lead.dm_variant_b = dm_variant_b
    lead.dm_variant_used = dm_variant_used
    lead.reply_text = reply_text
    lead.reply_classification = reply_classification
    lead.conversation_status = conversation_status
    lead.sent_at = sent_at or datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
    lead.replied_at = replied_at
    lead.follow_up_count = follow_up_count
    lead.comment_message = comment_message
    lead.comment_sent_at = comment_sent_at
    return lead


def _make_mock_db(leads=None):
    """Create a mock async DB session."""
    db = AsyncMock()

    if leads is not None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = leads
        mock_result.scalars.return_value = mock_scalars
        mock_result.scalar.return_value = len(leads)
        db.execute.return_value = mock_result

    return db


# ------------------------------------------------------------------ #
# Tests: _lead_to_conversation
# ------------------------------------------------------------------ #
class TestLeadToConversation:
    """Tests for converting a Lead ORM to conversation summary dict."""

    def test_basic_conversion(self):
        service = UniboxService()
        lead = _make_lead()
        conv = service._lead_to_conversation(lead)

        assert conv["ig_username"] == "testlead"
        assert conv["ig_full_name"] == "Test Lead"
        assert conv["score"] == 75
        assert conv["has_reply"] is False
        assert conv["conversation_status"] == "awaiting_reply"
        assert conv["lead_id"] == str(lead.id)
        assert conv["campaign_id"] == str(lead.campaign_id)

    def test_with_reply(self):
        service = UniboxService()
        lead = _make_lead(
            reply_text="Sounds interesting, tell me more!",
            reply_classification="positive",
            replied_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
            conversation_status="replied",
        )
        conv = service._lead_to_conversation(lead)

        assert conv["has_reply"] is True
        assert conv["reply_classification"] == "positive"
        assert conv["conversation_status"] == "replied"
        assert "Sounds interesting" in conv["last_message_preview"]

    def test_long_message_truncated(self):
        service = UniboxService()
        lead = _make_lead(dm_message="A" * 200)
        conv = service._lead_to_conversation(lead)

        assert len(conv["last_message_preview"]) <= 103  # 100 + "..."
        assert conv["last_message_preview"].endswith("...")

    def test_no_message(self):
        service = UniboxService()
        lead = _make_lead(dm_message=None)
        conv = service._lead_to_conversation(lead)

        assert conv["last_message_preview"] is None


# ------------------------------------------------------------------ #
# Tests: get_conversation_thread
# ------------------------------------------------------------------ #
class TestGetConversationThread:
    """Tests for retrieving full conversation thread."""

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_lead(self):
        service = UniboxService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.get_conversation_thread("nonexistent-id", db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_thread_from_lead_fields(self):
        """When no conversation_messages exist, reconstruct from lead fields."""
        service = UniboxService()
        lead = _make_lead(
            reply_text="Tell me more!",
            replied_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
        )

        db = AsyncMock()
        db.get.return_value = lead

        # Mock: no stored conversation_messages
        empty_result = MagicMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result.scalars.return_value = empty_scalars

        # Mock: no stored suggestions
        no_sugg = MagicMock()
        no_sugg.scalar_one_or_none.return_value = None

        db.execute.side_effect = [empty_result, no_sugg]

        result = await service.get_conversation_thread(str(lead.id), db)

        assert result is not None
        assert result["lead"]["ig_username"] == "testlead"
        assert len(result["messages"]) == 2
        assert result["messages"][0]["direction"] == "outbound"
        assert result["messages"][0]["content"] == "Hey! Love your content."
        assert result["messages"][1]["direction"] == "inbound"
        assert result["messages"][1]["content"] == "Tell me more!"
        assert result["suggestions"] is None


# ------------------------------------------------------------------ #
# Tests: generate_reply_suggestions
# ------------------------------------------------------------------ #
class TestGenerateReplySuggestions:
    """Tests for AI reply suggestion generation."""

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_lead(self):
        service = UniboxService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.generate_reply_suggestions("nonexistent", db)
        assert result is None

    @pytest.mark.asyncio
    async def test_generates_suggestions_successfully(self):
        service = UniboxService()

        lead = _make_lead(
            reply_text="How much does it cost?",
            replied_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
        )
        campaign = MagicMock()
        campaign.name = "Test Campaign"
        campaign.settings = {}
        client = MagicMock()
        client.name = "Test Client"
        client.settings = {"dm_prompt": "We sell AI automation"}

        db = AsyncMock()

        # get_conversation_thread needs db.get to return lead, then execute for messages and suggestions
        def mock_get(model_class, id_val):
            if str(id_val) == str(lead.id) or id_val == str(lead.id):
                return lead
            if str(id_val) == str(lead.campaign_id):
                return campaign
            if str(id_val) == str(lead.client_id):
                return client
            return lead  # default fallback

        db.get.side_effect = mock_get

        # Mock execute for: conversation_messages query, suggestions query
        empty_result = MagicMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result.scalars.return_value = empty_scalars

        no_sugg = MagicMock()
        no_sugg.scalar_one_or_none.return_value = None

        db.execute.side_effect = [empty_result, no_sugg]

        suggestions_json = json.dumps([
            {"intent": "close", "label": "Agendar llamada", "message": "El precio depende del plan..."},
            {"intent": "nurture", "label": "Responder precio", "message": "Tenemos 3 planes..."},
            {"intent": "qualify", "label": "Calificar", "message": "Para darte un precio exacto..."},
        ])

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=suggestions_json)]

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = await service.generate_reply_suggestions(str(lead.id), db)

        assert result is not None
        assert len(result["suggestions"]) == 3
        assert result["suggestions"][0]["intent"] == "close"
        assert result["suggestions"][1]["intent"] == "nurture"
        assert result["suggestions"][2]["intent"] == "qualify"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        service = UniboxService()
        lead = _make_lead(
            reply_text="Tell me more",
            replied_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
        )
        campaign = MagicMock()
        campaign.name = "Test"
        campaign.settings = {}
        client_obj = MagicMock()
        client_obj.name = "Client"
        client_obj.settings = {}

        db = AsyncMock()

        async def mock_get(cls, id_val):
            id_str = str(id_val)
            if id_str == str(lead.id):
                return lead
            if id_str == str(lead.campaign_id):
                return campaign
            return client_obj

        db.get = mock_get

        empty_result = MagicMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result.scalars.return_value = empty_scalars
        no_sugg = MagicMock()
        no_sugg.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[empty_result, no_sugg])

        with patch.object(service, "_get_anthropic_client") as mock_client:
            mock_client.return_value.messages.create.side_effect = Exception("API Error")
            result = await service.generate_reply_suggestions(str(lead.id), db)

        assert result is None


# ------------------------------------------------------------------ #
# Tests: auto_suggest_on_new_reply
# ------------------------------------------------------------------ #
class TestAutoSuggestOnNewReply:
    """Tests for automatic suggestion generation on new replies."""

    @pytest.mark.asyncio
    async def test_skips_spam_classification(self):
        service = UniboxService()
        lead = _make_lead(
            reply_text="Buy cheap followers!!",
            reply_classification="spam",
        )

        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_suggest_on_new_reply(str(lead.id), db)
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_not_interested(self):
        service = UniboxService()
        lead = _make_lead(
            reply_text="No thanks",
            reply_classification="not_interested",
        )

        db = AsyncMock()
        db.get.return_value = lead

        result = await service.auto_suggest_on_new_reply(str(lead.id), db)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_lead(self):
        service = UniboxService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.auto_suggest_on_new_reply("nonexistent", db)
        assert result is False


# ------------------------------------------------------------------ #
# Tests: get_suggestions
# ------------------------------------------------------------------ #
class TestGetSuggestions:
    """Tests for retrieving pre-generated suggestions."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_suggestions(self):
        service = UniboxService()
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await service.get_suggestions("some-lead-id", db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_suggestions_when_exist(self):
        service = UniboxService()
        db = AsyncMock()

        mock_sugg = MagicMock()
        mock_sugg.suggestions = [
            {"intent": "close", "label": "Close", "message": "Let's schedule a call"},
        ]
        mock_sugg.generated_at = datetime(2026, 3, 21, 14, 0, tzinfo=timezone.utc)
        mock_sugg.was_used = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sugg
        db.execute.return_value = mock_result

        result = await service.get_suggestions("some-lead-id", db)
        assert result is not None
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["intent"] == "close"
        assert result["was_used"] is False


# ------------------------------------------------------------------ #
# Tests: send_reply
# ------------------------------------------------------------------ #
class TestSendReply:
    """Tests for sending manual replies via Unibox."""

    @pytest.mark.asyncio
    async def test_returns_error_for_nonexistent_lead(self):
        service = UniboxService()
        db = AsyncMock()
        db.get.return_value = None

        result = await service.send_reply("nonexistent", "Hello", db)
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_returns_error_when_login_fails(self):
        service = UniboxService()
        lead = _make_lead()
        db = AsyncMock()
        db.get.return_value = lead

        mock_sender = MagicMock()
        mock_sender.login.return_value = False

        with patch("app.services.dm_sender_service.dm_sender_service", mock_sender):
            result = await service.send_reply(str(lead.id), "Hello", db)

        assert result["success"] is False
        assert "login failed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_successful_reply_stores_message(self):
        service = UniboxService()
        lead = _make_lead()
        db = AsyncMock()
        db.get.return_value = lead

        mock_sender = MagicMock()
        mock_sender.login.return_value = True
        mock_sender.send_dm.return_value = {"success": True}
        mock_sender._accounts = [MagicMock(username="bot_account", _logged_in=True)]
        mock_sender.save_sessions = MagicMock()

        with patch("app.services.dm_sender_service.dm_sender_service", mock_sender):
            result = await service.send_reply(str(lead.id), "Thanks for your interest!", db)

        assert result["success"] is True
        db.add.assert_called_once()  # ConversationMessage was added
        db.commit.assert_called_once()


# ------------------------------------------------------------------ #
# Tests: mark_suggestion_used
# ------------------------------------------------------------------ #
class TestMarkSuggestionUsed:
    """Tests for marking suggestions as used."""

    @pytest.mark.asyncio
    async def test_marks_suggestion_used(self):
        service = UniboxService()
        db = AsyncMock()

        mock_sugg = MagicMock()
        mock_sugg.was_used = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sugg
        db.execute.return_value = mock_result

        await service.mark_suggestion_used("some-lead-id", db)

        assert mock_sugg.was_used is True
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_error_when_no_suggestion(self):
        service = UniboxService()
        db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        # Should not raise
        await service.mark_suggestion_used("some-lead-id", db)
        db.commit.assert_not_called()
