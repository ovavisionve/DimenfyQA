import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.services.copywriting_service import (
    CopywritingService,
    _strip_code_fences,
    DM_BATCH_SIZE,
)


@pytest.fixture
def copywriting_service():
    with patch("app.services.copywriting_service.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_settings.DM_SCORE_THRESHOLD = 70
        service = CopywritingService()
        return service


def _make_claude_response(text: str) -> MagicMock:
    """Helper to build a mock Claude API response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    return mock_response


class TestStripCodeFences:
    def test_strips_json_fences(self):
        raw = '```json\n{"dm_a": "hello"}\n```'
        assert _strip_code_fences(raw) == '{"dm_a": "hello"}'

    def test_strips_plain_fences(self):
        raw = '```\n{"dm_a": "hello"}\n```'
        assert _strip_code_fences(raw) == '{"dm_a": "hello"}'

    def test_no_fences_unchanged(self):
        raw = '{"dm_a": "hello"}'
        assert _strip_code_fences(raw) == '{"dm_a": "hello"}'


class TestGenerateSingleDm:
    def test_returns_dm_a_and_dm_b(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        response_json = json.dumps({
            "dm_a": "Hey Test, vi tu agencia de marketing y me parecio interesante tu enfoque. Nosotros ayudamos a automatizar leads. Te interesa?",
            "dm_b": "Test, me llamo la atencion tu perfil. Estamos trabajando con agencias similares en algo que funciona bien. Quieres saber mas?",
        })
        mock_response = _make_claude_response(response_json)

        lead_data = {**sample_lead_data, "research_data": "Marketing agency in Miami"}

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            dm_a, dm_b = copywriting_service.generate_single_dm(lead_data, sample_client_config)

        assert dm_a is not None
        assert dm_b is not None
        assert isinstance(dm_a, str)
        assert isinstance(dm_b, str)
        assert len(dm_a) > 0
        assert len(dm_b) > 0

    def test_returns_none_none_on_api_error(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        with patch.object(
            copywriting_service.client.messages, "create", side_effect=Exception("API error")
        ):
            dm_a, dm_b = copywriting_service.generate_single_dm(sample_lead_data, sample_client_config)

        assert dm_a is None
        assert dm_b is None

    def test_returns_none_none_on_invalid_json(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        mock_response = _make_claude_response("not valid json at all")

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            dm_a, dm_b = copywriting_service.generate_single_dm(sample_lead_data, sample_client_config)

        assert dm_a is None
        assert dm_b is None

    def test_handles_code_fences_in_response(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        response_json = '```json\n{"dm_a": "Hola", "dm_b": "Hey"}\n```'
        mock_response = _make_claude_response(response_json)

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            dm_a, dm_b = copywriting_service.generate_single_dm(sample_lead_data, sample_client_config)

        assert dm_a == "Hola"
        assert dm_b == "Hey"

    def test_no_research_data_uses_default(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        response_json = json.dumps({
            "dm_a": "Hey, vi tu perfil y me parecio interesante.",
            "dm_b": "Hola, me llamo la atencion tu perfil.",
        })
        mock_response = _make_claude_response(response_json)

        lead_data = {**sample_lead_data}  # no research_data key

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ) as mock_create:
            dm_a, dm_b = copywriting_service.generate_single_dm(lead_data, sample_client_config)

        assert dm_a is not None
        # Verify "No research available" is in the prompt
        call_args = mock_create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "No research available" in prompt

    def test_uses_bio_clean_over_bio(
        self, copywriting_service, sample_client_config
    ):
        response_json = json.dumps({"dm_a": "test a", "dm_b": "test b"})
        mock_response = _make_claude_response(response_json)

        lead_data = {
            "ig_username": "testuser",
            "ig_full_name": "Test",
            "ig_bio": "raw bio with emojis",
            "ig_bio_clean": "clean bio without emojis",
            "ig_website": "",
            "lead_category": "Agency",
            "research_data": "Some research",
        }

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ) as mock_create:
            copywriting_service.generate_single_dm(lead_data, sample_client_config)

        prompt = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "clean bio without emojis" in prompt

    def test_falls_back_to_bio_when_no_bio_clean(
        self, copywriting_service, sample_client_config
    ):
        response_json = json.dumps({"dm_a": "test a", "dm_b": "test b"})
        mock_response = _make_claude_response(response_json)

        lead_data = {
            "ig_username": "testuser",
            "ig_full_name": "Test",
            "ig_bio": "raw bio here",
            "ig_bio_clean": None,
            "ig_website": "",
            "lead_category": "Agency",
            "research_data": "Some research",
        }

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ) as mock_create:
            copywriting_service.generate_single_dm(lead_data, sample_client_config)

        prompt = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "raw bio here" in prompt


class TestGenerateDmsBatch:
    def test_returns_list_of_dicts(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        batch_response = json.dumps([
            {"username": "testbusiness", "dm_a": "DM A for test", "dm_b": "DM B for test"},
        ])
        mock_response = _make_claude_response(batch_response)

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            results = copywriting_service.generate_dms_batch(
                [sample_lead_data], sample_client_config
            )

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["username"] == "testbusiness"
        assert "dm_a" in results[0]
        assert "dm_b" in results[0]

    def test_multiple_leads_in_batch(
        self, copywriting_service, sample_client_config
    ):
        leads = [
            {"ig_username": f"user{i}", "ig_full_name": f"User {i}", "ig_bio": "Bio", "ig_website": "", "lead_category": "Agency", "research_data": "research"}
            for i in range(3)
        ]
        batch_response = json.dumps([
            {"username": f"user{i}", "dm_a": f"DM A {i}", "dm_b": f"DM B {i}"}
            for i in range(3)
        ])
        mock_response = _make_claude_response(batch_response)

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            results = copywriting_service.generate_dms_batch(leads, sample_client_config)

        assert len(results) == 3

    def test_raises_on_non_array_response(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        mock_response = _make_claude_response('{"not": "an array"}')

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            with pytest.raises(ValueError, match="Expected JSON array"):
                copywriting_service.generate_dms_batch(
                    [sample_lead_data], sample_client_config
                )

    def test_raises_on_api_error(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        with patch.object(
            copywriting_service.client.messages, "create", side_effect=Exception("API down")
        ):
            with pytest.raises(Exception, match="API down"):
                copywriting_service.generate_dms_batch(
                    [sample_lead_data], sample_client_config
                )


class TestGenerateDmsBatchSafe:
    def test_batch_success_returns_tuples(
        self, copywriting_service, sample_client_config
    ):
        leads = [
            {"ig_username": "user1", "ig_full_name": "User 1", "ig_bio": "Bio"},
            {"ig_username": "user2", "ig_full_name": "User 2", "ig_bio": "Bio"},
        ]
        batch_response = json.dumps([
            {"username": "user1", "dm_a": "DM A1", "dm_b": "DM B1"},
            {"username": "user2", "dm_a": "DM A2", "dm_b": "DM B2"},
        ])
        mock_response = _make_claude_response(batch_response)

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            results = copywriting_service._generate_dms_batch_safe(leads, sample_client_config)

        assert len(results) == 2
        # Each result is (username, dm_a, dm_b)
        assert results[0] == ("user1", "DM A1", "DM B1")
        assert results[1] == ("user2", "DM A2", "DM B2")

    def test_falls_back_to_individual_on_batch_error(
        self, copywriting_service, sample_client_config
    ):
        leads = [
            {"ig_username": "user1", "ig_full_name": "User 1", "ig_bio": "Bio"},
        ]

        single_response = json.dumps({"dm_a": "Individual A", "dm_b": "Individual B"})

        with patch.object(
            copywriting_service, "generate_dms_batch", side_effect=Exception("batch failed")
        ), patch.object(
            copywriting_service, "generate_single_dm", return_value=("Individual A", "Individual B")
        ) as mock_single:
            results = copywriting_service._generate_dms_batch_safe(leads, sample_client_config)

        assert len(results) == 1
        assert results[0] == ("user1", "Individual A", "Individual B")
        mock_single.assert_called_once()

    def test_retries_missing_leads_individually(
        self, copywriting_service, sample_client_config
    ):
        """When batch returns results for only some leads, missing ones are retried individually."""
        leads = [
            {"ig_username": "user1", "ig_full_name": "User 1", "ig_bio": "Bio"},
            {"ig_username": "user2", "ig_full_name": "User 2", "ig_bio": "Bio"},
        ]

        # Batch only returns user1, not user2
        batch_result = [{"username": "user1", "dm_a": "Batch A1", "dm_b": "Batch B1"}]

        with patch.object(
            copywriting_service, "generate_dms_batch", return_value=batch_result
        ), patch.object(
            copywriting_service, "generate_single_dm", return_value=("Single A2", "Single B2")
        ) as mock_single:
            results = copywriting_service._generate_dms_batch_safe(leads, sample_client_config)

        assert len(results) == 2
        # user1 from batch
        assert ("user1", "Batch A1", "Batch B1") in results
        # user2 from individual fallback
        assert ("user2", "Single A2", "Single B2") in results
        mock_single.assert_called_once_with(leads[1], sample_client_config)


class TestWriteDmsBatch:
    """Tests for the async write_dms_batch method that orchestrates DB + DM generation."""

    @pytest.fixture
    def mock_lead(self):
        """Create a mock Lead ORM object."""
        def _make_lead(username="testuser", score=80, status="researched"):
            lead = MagicMock()
            lead.id = uuid.uuid4()
            lead.ig_username = username
            lead.ig_full_name = f"Full Name {username}"
            lead.ig_bio = "Test bio"
            lead.ig_bio_clean = "Clean test bio"
            lead.ig_website = "https://example.com"
            lead.ig_category = "Agency"
            lead.ig_follower_count = 5000
            lead.ig_following_count = 500
            lead.lead_category = "Agency"
            lead.research_data = "Some research data"
            lead.score = score
            lead.status = status
            lead.client_id = uuid.uuid4()
            lead.dm_message = None
            lead.dm_variant_b = None
            lead.dm_generated_at = None
            return lead
        return _make_lead

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.id = uuid.uuid4()
        client.business_type = "B2B automation agency"
        client.settings = {"service_description": "We automate lead gen with AI."}
        return client

    @pytest.mark.asyncio
    async def test_write_dms_batch_generates_dms(
        self, copywriting_service, mock_lead, mock_client
    ):
        lead1 = mock_lead("user1", score=85, status="researched")
        lead2 = mock_lead("user2", score=75, status="scored")

        # Mock client_id to match
        lead2.client_id = lead1.client_id
        mock_client.id = lead1.client_id

        lead_ids = [str(lead1.id), str(lead2.id)]

        # Mock DB session
        db = AsyncMock(spec=["execute", "flush"])

        # First query: select leads
        leads_result = MagicMock()
        leads_result.scalars.return_value.all.return_value = [lead1, lead2]

        # Second query: select client
        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = mock_client

        db.execute = AsyncMock(side_effect=[leads_result, client_result])
        db.flush = AsyncMock()

        # Mock the batch generation
        with patch.object(
            copywriting_service,
            "_generate_dms_batch_safe",
            return_value=[
                ("user1", "DM A for user1", "DM B for user1"),
                ("user2", "DM A for user2", "DM B for user2"),
            ],
        ):
            result_ids = await copywriting_service.write_dms_batch(lead_ids, db)

        assert len(result_ids) == 2
        assert lead1.dm_message == "DM A for user1"
        assert lead1.dm_variant_b == "DM B for user1"
        assert lead1.status == "dm_ready"
        assert lead1.dm_generated_at is not None
        assert lead2.dm_message == "DM A for user2"
        assert lead2.dm_variant_b == "DM B for user2"
        assert lead2.status == "dm_ready"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_dms_batch_returns_empty_when_no_qualifying_leads(
        self, copywriting_service
    ):
        db = AsyncMock(spec=["execute", "flush"])

        leads_result = MagicMock()
        leads_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=leads_result)

        result_ids = await copywriting_service.write_dms_batch(["some-id"], db)
        assert result_ids == []

    @pytest.mark.asyncio
    async def test_write_dms_batch_skips_leads_with_failed_generation(
        self, copywriting_service, mock_lead, mock_client
    ):
        lead1 = mock_lead("user1", score=80)
        mock_client.id = lead1.client_id

        lead_ids = [str(lead1.id)]

        db = AsyncMock(spec=["execute", "flush"])

        leads_result = MagicMock()
        leads_result.scalars.return_value.all.return_value = [lead1]

        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = mock_client

        db.execute = AsyncMock(side_effect=[leads_result, client_result])
        db.flush = AsyncMock()

        # DM generation returns None for dm_a (failed)
        with patch.object(
            copywriting_service,
            "_generate_dms_batch_safe",
            return_value=[("user1", None, None)],
        ):
            result_ids = await copywriting_service.write_dms_batch(lead_ids, db)

        assert len(result_ids) == 0
        assert lead1.dm_message is None
        assert lead1.status != "dm_ready"

    @pytest.mark.asyncio
    async def test_write_dms_batch_calls_progress_callback(
        self, copywriting_service, mock_lead, mock_client
    ):
        lead1 = mock_lead("user1", score=80)
        mock_client.id = lead1.client_id

        db = AsyncMock(spec=["execute", "flush"])

        leads_result = MagicMock()
        leads_result.scalars.return_value.all.return_value = [lead1]

        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = mock_client

        db.execute = AsyncMock(side_effect=[leads_result, client_result])
        db.flush = AsyncMock()

        progress_cb = MagicMock()

        with patch.object(
            copywriting_service,
            "_generate_dms_batch_safe",
            return_value=[("user1", "DM A", "DM B")],
        ):
            await copywriting_service.write_dms_batch(
                [str(lead1.id)], db, progress_callback=progress_cb
            )

        progress_cb.assert_called_once_with(1, 1, "user1")

    @pytest.mark.asyncio
    async def test_write_dms_batch_uses_client_config_from_db(
        self, copywriting_service, mock_lead, mock_client
    ):
        lead1 = mock_lead("user1", score=80)
        mock_client.id = lead1.client_id
        mock_client.business_type = "Real Estate Agency"
        mock_client.settings = {"service_description": "We sell houses with AI."}

        db = AsyncMock(spec=["execute", "flush"])

        leads_result = MagicMock()
        leads_result.scalars.return_value.all.return_value = [lead1]

        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = mock_client

        db.execute = AsyncMock(side_effect=[leads_result, client_result])
        db.flush = AsyncMock()

        with patch.object(
            copywriting_service,
            "_generate_dms_batch_safe",
            return_value=[("user1", "DM A", "DM B")],
        ) as mock_batch:
            await copywriting_service.write_dms_batch([str(lead1.id)], db)

        # Verify client config was passed correctly
        call_args = mock_batch.call_args
        client_config = call_args[0][1]  # second positional arg
        assert client_config["business_type"] == "Real Estate Agency"
        assert client_config["service_description"] == "We sell houses with AI."


class TestCallClaude:
    def test_calls_correct_model(self, copywriting_service):
        mock_response = _make_claude_response("test response")

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ) as mock_create:
            result = copywriting_service._call_claude("test prompt")

        mock_create.assert_called_once_with(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": "test prompt"}],
        )
        assert result == "test response"

    def test_custom_max_tokens(self, copywriting_service):
        mock_response = _make_claude_response("test")

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ) as mock_create:
            copywriting_service._call_claude("prompt", max_tokens=1024)

        assert mock_create.call_args.kwargs["max_tokens"] == 1024
