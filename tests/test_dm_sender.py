"""Tests for Phase 2 DM sending: service, task, enums, config, and schema."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.schemas.enums import CampaignStatus, LeadStatus


class TestPhase2Enums:
    """Verify new enum values for Phase 2."""

    def test_campaign_status_sending(self):
        assert CampaignStatus.SENDING == "sending"

    def test_campaign_status_completed(self):
        assert CampaignStatus.COMPLETED == "completed"

    def test_campaign_status_paused(self):
        assert CampaignStatus.PAUSED == "paused"

    def test_lead_status_sending(self):
        assert LeadStatus.SENDING == "sending"

    def test_lead_status_delivered(self):
        assert LeadStatus.DELIVERED == "delivered"

    def test_lead_status_retry(self):
        assert LeadStatus.RETRY == "retry"

    def test_lead_status_sent(self):
        assert LeadStatus.SENT == "sent"


class TestPhase2Config:
    """Verify DM sending config defaults."""

    def test_ig_username_default_empty(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.IG_USERNAME == ""

    def test_ig_password_default_empty(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.IG_PASSWORD == ""

    def test_daily_dm_limit_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.DAILY_DM_LIMIT == 30

    def test_dm_delay_min_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.DM_DELAY_MIN == 45

    def test_dm_delay_max_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.DM_DELAY_MAX == 120

    def test_proxy_url_default_empty(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.PROXY_URL == ""

    def test_ig_session_dir_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.IG_SESSION_DIR == "./ig_sessions"


class TestCampaignStatsSchema:
    """Verify CampaignStats includes sent/failed fields."""

    def test_campaign_stats_has_sent_leads(self):
        from app.schemas.campaign import CampaignStats
        stats = CampaignStats(
            campaign_id=uuid.uuid4(),
            total_leads=100,
            sent_leads=50,
            failed_leads=5,
            status="completed",
        )
        assert stats.sent_leads == 50
        assert stats.failed_leads == 5

    def test_campaign_stats_defaults_zero(self):
        from app.schemas.campaign import CampaignStats
        stats = CampaignStats(
            campaign_id=uuid.uuid4(),
            status="pending",
        )
        assert stats.sent_leads == 0
        assert stats.failed_leads == 0


class TestLeadSchemaPhase2:
    """Verify LeadRead includes Phase 2 fields."""

    def test_lead_read_has_send_fields(self):
        from app.schemas.lead import LeadRead
        fields = LeadRead.model_fields
        assert "send_attempts" in fields
        assert "send_error" in fields
        assert "delivery_status" in fields
        assert "dm_variant_used" in fields
        assert "sent_at" in fields


class TestDMSenderService:
    """Unit tests for DMSenderService."""

    def test_service_init_creates_session_dir(self, tmp_path):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = str(tmp_path / "sessions")
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            mock_settings.PROXY_URL = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            assert svc._session_path.exists()

    def test_login_fails_without_credentials(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            mock_settings.PROXY_URL = ""
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            result = svc.login()
            assert result is False

    def test_send_dm_fails_when_not_logged_in(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.PROXY_URL = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._logged_in = False
            result = svc.send_dm("testuser", "Hello")
            assert result["success"] is False
            assert "Not logged in" in result["error"]

    def test_send_dm_detects_challenge(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.PROXY_URL = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._logged_in = True
            svc._client = MagicMock()
            svc._client.user_id_from_username.side_effect = Exception("challenge_required")
            result = svc.send_dm("testuser", "Hello")
            assert result["success"] is False
            assert result["is_challenge"] is True

    def test_send_dm_detects_block(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.PROXY_URL = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._logged_in = True
            svc._client = MagicMock()
            svc._client.user_id_from_username.side_effect = Exception("feedback_required: block")
            result = svc.send_dm("testuser", "Hello")
            assert result["success"] is False
            assert result["is_block"] is True

    def test_send_dm_success(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.PROXY_URL = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._logged_in = True
            svc._client = MagicMock()
            svc._client.user_id_from_username.return_value = "12345"
            mock_result = MagicMock()
            mock_result.id = "thread_abc"
            svc._client.direct_send.return_value = mock_result
            result = svc.send_dm("testuser", "Hello!")
            assert result["success"] is True
            assert result["thread_id"] == "thread_abc"


class TestSendingTaskConfig:
    """Verify sending task is properly configured."""

    def test_sending_task_has_retry(self):
        from app.tasks.sending_tasks import send_dms_task
        assert send_dms_task.max_retries == 3

    def test_sending_task_name(self):
        from app.tasks.sending_tasks import send_dms_task
        assert send_dms_task.name == "send_dms"

    def test_pipeline_includes_sending(self):
        """Verify the pipeline chain includes the sending task."""
        from app.tasks.pipeline import run_campaign_pipeline
        import inspect
        source = inspect.getsource(run_campaign_pipeline)
        assert "send_dms_task" in source


class TestMigration003:
    """Verify migration file exists and has correct structure."""

    def test_migration_file_exists(self):
        from pathlib import Path
        migration = Path("alembic/versions/003_add_phase2_sending_fields.py")
        assert migration.exists()

    def test_migration_adds_columns(self):
        from pathlib import Path
        content = Path("alembic/versions/003_add_phase2_sending_fields.py").read_text()
        assert "send_attempts" in content
        assert "send_error" in content
        assert "delivery_status" in content
        assert "dm_variant_used" in content

    def test_migration_creates_indexes(self):
        from pathlib import Path
        content = Path("alembic/versions/003_add_phase2_sending_fields.py").read_text()
        assert "idx_leads_delivery_status" in content
        assert "idx_leads_send_attempts" in content

    def test_migration_revision_chain(self):
        from pathlib import Path
        content = Path("alembic/versions/003_add_phase2_sending_fields.py").read_text()
        assert 'revision = "003"' in content
        assert 'down_revision = "002"' in content
