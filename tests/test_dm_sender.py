"""Tests for Phase 2 DM sending: service, task, enums, config, security, and schema."""
import uuid
from datetime import datetime, timedelta, timezone
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
    """Verify DM sending config defaults including security settings."""

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

    def test_ig_accounts_default_empty(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.IG_ACCOUNTS == ""

    def test_warmup_days_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.IG_WARMUP_DAYS == 7

    def test_warmup_start_limit_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.IG_WARMUP_START_LIMIT == 5

    # Security config defaults
    def test_hourly_dm_limit_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.HOURLY_DM_LIMIT == 10

    def test_challenge_cooldown_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.CHALLENGE_COOLDOWN_MINUTES == 60

    def test_block_cooldown_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.BLOCK_COOLDOWN_HOURS == 24

    def test_max_challenges_before_pause_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.MAX_CHALLENGES_BEFORE_PAUSE == 3

    def test_pre_send_check_public_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.PRE_SEND_CHECK_PUBLIC is True

    def test_skip_private_accounts_default(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.SKIP_PRIVATE_ACCOUNTS is True

    def test_encryption_key_default_empty(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x", REDIS_URL="redis://x")
        assert s.IG_SESSION_ENCRYPTION_KEY == ""


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


class TestParseAccounts:
    """Test multi-account config parsing."""

    def test_parse_empty(self):
        from app.services.dm_sender_service import _parse_accounts
        assert _parse_accounts("") == []
        assert _parse_accounts("  ") == []

    def test_parse_single_account(self):
        from app.services.dm_sender_service import _parse_accounts
        result = _parse_accounts("bot1:pass1:http://proxy1:8080")
        assert len(result) == 1
        assert result[0]["username"] == "bot1"
        assert result[0]["password"] == "pass1"
        assert result[0]["proxy"] == "http://proxy1:8080"

    def test_parse_multiple_accounts(self):
        from app.services.dm_sender_service import _parse_accounts
        result = _parse_accounts("bot1:pass1:http://p1,bot2:pass2:http://p2")
        assert len(result) == 2
        assert result[0]["username"] == "bot1"
        assert result[1]["username"] == "bot2"

    def test_parse_account_without_proxy(self):
        from app.services.dm_sender_service import _parse_accounts
        result = _parse_accounts("bot1:pass1")
        assert len(result) == 1
        assert result[0]["proxy"] == ""


class TestIGAccount:
    """Unit tests for IGAccount class."""

    def test_warmup_limit_new_account(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc.created_at = None
        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_WARMUP_START_LIMIT = 5
            s.IG_WARMUP_DAYS = 7
            s.DAILY_DM_LIMIT = 30
            assert acc.get_warmup_limit() == 5

    def test_warmup_limit_mature_account(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_WARMUP_START_LIMIT = 5
            s.IG_WARMUP_DAYS = 7
            s.DAILY_DM_LIMIT = 30
            assert acc.get_warmup_limit() == 30

    def test_warmup_limit_mid_warmup(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        # 3.5 days into a 7-day warmup: should be ~halfway (5 + (30-5)*0.5 = 17)
        acc.created_at = datetime.now(timezone.utc).replace(hour=0) - __import__('datetime').timedelta(days=3)
        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_WARMUP_START_LIMIT = 5
            s.IG_WARMUP_DAYS = 7
            s.DAILY_DM_LIMIT = 30
            limit = acc.get_warmup_limit()
            assert 10 <= limit <= 20  # Roughly halfway

    def test_health_metrics(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc._logged_in = True
        acc.total_sent = 10
        acc.total_failed = 2
        acc.challenges = 1
        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_WARMUP_START_LIMIT = 5
            s.IG_WARMUP_DAYS = 7
            s.DAILY_DM_LIMIT = 30
            s.HOURLY_DM_LIMIT = 10
            s.CHALLENGE_COOLDOWN_MINUTES = 60
            s.BLOCK_COOLDOWN_HOURS = 24
            s.MAX_CHALLENGES_BEFORE_PAUSE = 3
            health = acc.get_health()
        assert health["username"] == "test"
        assert health["logged_in"] is True
        assert health["total_sent"] == 10
        assert health["total_failed"] == 2
        assert health["success_rate"] == 83.3
        assert "in_cooldown" in health
        assert "hourly_sends" in health

    def test_health_persistence(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc1 = IGAccount("test", "pass", "", tmp_path)
        acc1.total_sent = 50
        acc1.total_failed = 3
        acc1.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        acc1.last_challenge_at = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        acc1.challenges_today = 2
        acc1._challenges_today_date = "2025-06-01"
        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_SESSION_ENCRYPTION_KEY = ""
            acc1._save_health()

        acc2 = IGAccount("test", "pass", "", tmp_path)
        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_SESSION_ENCRYPTION_KEY = ""
            acc2._load_health()
        assert acc2.total_sent == 50
        assert acc2.total_failed == 3
        assert acc2.created_at == datetime(2025, 6, 1, tzinfo=timezone.utc)
        assert acc2.last_challenge_at == datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        assert acc2.challenges_today == 2

    def test_send_dm_fails_when_not_logged_in(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        result = acc.send_dm("testuser", "Hello")
        assert result["success"] is False
        assert "Not logged in" in result["error"]

    def test_send_dm_detects_challenge(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc._logged_in = True
        acc._client = MagicMock()
        acc._client.user_id_from_username.side_effect = Exception("challenge_required")
        with patch("app.services.dm_sender_service.settings") as s:
            s.HOURLY_DM_LIMIT = 10
            s.CHALLENGE_COOLDOWN_MINUTES = 60
            s.BLOCK_COOLDOWN_HOURS = 24
            s.MAX_CHALLENGES_BEFORE_PAUSE = 3
            s.IG_SESSION_ENCRYPTION_KEY = ""
            result = acc.send_dm("testuser", "Hello")
        assert result["success"] is False
        assert result["is_challenge"] is True
        assert acc.challenges == 1
        assert acc.last_challenge_at is not None

    def test_send_dm_detects_block(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc._logged_in = True
        acc._client = MagicMock()
        acc._client.user_id_from_username.side_effect = Exception("feedback_required: block")
        with patch("app.services.dm_sender_service.settings") as s:
            s.HOURLY_DM_LIMIT = 10
            s.CHALLENGE_COOLDOWN_MINUTES = 60
            s.BLOCK_COOLDOWN_HOURS = 24
            s.MAX_CHALLENGES_BEFORE_PAUSE = 3
            s.IG_SESSION_ENCRYPTION_KEY = ""
            result = acc.send_dm("testuser", "Hello")
        assert result["success"] is False
        assert result["is_block"] is True
        assert acc.is_blocked is True
        assert acc.last_block_at is not None

    def test_send_dm_success(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc._logged_in = True
        acc._client = MagicMock()
        acc._client.user_id_from_username.return_value = "12345"
        mock_result = MagicMock()
        mock_result.id = "thread_abc"
        acc._client.direct_send.return_value = mock_result
        with patch("app.services.dm_sender_service.settings") as s:
            s.HOURLY_DM_LIMIT = 10
            s.CHALLENGE_COOLDOWN_MINUTES = 60
            s.BLOCK_COOLDOWN_HOURS = 24
            s.MAX_CHALLENGES_BEFORE_PAUSE = 3
            s.IG_SESSION_ENCRYPTION_KEY = ""
            with patch("app.services.dm_sender_service.time"):
                result = acc.send_dm("testuser", "Hello!")
        assert result["success"] is True
        assert result["thread_id"] == "thread_abc"
        assert acc.total_sent == 1

    def test_hourly_rate_limit(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc._logged_in = True
        acc._client = MagicMock()
        # Fill hourly sends to the limit
        import time as _time
        now = _time.time()
        with patch("app.services.dm_sender_service.settings") as s:
            s.HOURLY_DM_LIMIT = 3
            s.CHALLENGE_COOLDOWN_MINUTES = 60
            s.BLOCK_COOLDOWN_HOURS = 24
            s.MAX_CHALLENGES_BEFORE_PAUSE = 3
            acc._hourly_sends = [now - 10, now - 20, now - 30]
            result = acc.send_dm("testuser", "Hello!")
        assert result["success"] is False
        assert "Hourly DM limit" in result["error"]
        assert result.get("is_rate_limited") is True

    def test_cooldown_after_challenge(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc.last_challenge_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        with patch("app.services.dm_sender_service.settings") as s:
            s.CHALLENGE_COOLDOWN_MINUTES = 60
            s.BLOCK_COOLDOWN_HOURS = 24
            s.MAX_CHALLENGES_BEFORE_PAUSE = 3
            in_cooldown, reason = acc.is_in_cooldown()
        assert in_cooldown is True
        assert "Challenge cooldown" in reason

    def test_cooldown_expired(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        acc.last_challenge_at = datetime.now(timezone.utc) - timedelta(hours=2)
        with patch("app.services.dm_sender_service.settings") as s:
            s.CHALLENGE_COOLDOWN_MINUTES = 60
            s.BLOCK_COOLDOWN_HOURS = 24
            s.MAX_CHALLENGES_BEFORE_PAUSE = 3
            in_cooldown, _ = acc.is_in_cooldown()
        assert in_cooldown is False

    def test_too_many_challenges_today(self, tmp_path):
        from app.services.dm_sender_service import IGAccount
        acc = IGAccount("test", "pass", "", tmp_path)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        acc._challenges_today_date = today
        acc.challenges_today = 5
        with patch("app.services.dm_sender_service.settings") as s:
            s.CHALLENGE_COOLDOWN_MINUTES = 60
            s.BLOCK_COOLDOWN_HOURS = 24
            s.MAX_CHALLENGES_BEFORE_PAUSE = 3
            in_cooldown, reason = acc.is_in_cooldown()
        assert in_cooldown is True
        assert "Too many challenges" in reason

    def test_device_profile_consistent(self, tmp_path):
        """Same username always gets the same device profile."""
        from app.services.dm_sender_service import IGAccount
        acc1 = IGAccount("testuser", "pass", "", tmp_path)
        acc2 = IGAccount("testuser", "pass", "", tmp_path)
        assert acc1._device_profile == acc2._device_profile

    def test_device_profile_different_users(self, tmp_path):
        """Different usernames may get different device profiles."""
        from app.services.dm_sender_service import IGAccount
        # Just verify the profile is assigned without error
        acc1 = IGAccount("bot1", "pass", "", tmp_path)
        acc2 = IGAccount("bot2", "pass", "", tmp_path)
        assert acc1._device_profile is not None
        assert acc2._device_profile is not None


class TestDMSenderService:
    """Unit tests for DMSenderService."""

    def test_service_init_creates_session_dir(self, tmp_path):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = str(tmp_path / "sessions")
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            mock_settings.PROXY_URL = ""
            mock_settings.IG_ACCOUNTS = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            assert svc._session_path.exists()

    def test_login_fails_without_credentials(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            mock_settings.PROXY_URL = ""
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.IG_ACCOUNTS = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            result = svc.login()
            assert result is False

    def test_send_dm_fails_no_accounts(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.IG_ACCOUNTS = ""
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            result = svc.send_dm("testuser", "Hello")
            assert result["success"] is False
            assert "No available" in result["error"]

    def test_multi_account_init(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.IG_ACCOUNTS = "bot1:pass1:http://p1,bot2:pass2:http://p2"
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._init_accounts()
            assert len(svc._accounts) == 2
            assert svc._accounts[0].username == "bot1"
            assert svc._accounts[1].username == "bot2"

    def test_single_account_fallback(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.IG_ACCOUNTS = ""
            mock_settings.IG_USERNAME = "single_bot"
            mock_settings.IG_PASSWORD = "pass"
            mock_settings.PROXY_URL = ""
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._init_accounts()
            assert len(svc._accounts) == 1
            assert svc._accounts[0].username == "single_bot"

    def test_accounts_health(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.IG_ACCOUNTS = "bot1:pass1,bot2:pass2"
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            mock_settings.IG_WARMUP_START_LIMIT = 5
            mock_settings.IG_WARMUP_DAYS = 7
            mock_settings.DAILY_DM_LIMIT = 30
            mock_settings.HOURLY_DM_LIMIT = 10
            mock_settings.CHALLENGE_COOLDOWN_MINUTES = 60
            mock_settings.BLOCK_COOLDOWN_HOURS = 24
            mock_settings.MAX_CHALLENGES_BEFORE_PAUSE = 3
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            health = svc.get_accounts_health()
            assert len(health) == 2
            assert health[0]["username"] == "bot1"
            assert "success_rate" in health[0]
            assert "warmup_limit" in health[0]
            assert "in_cooldown" in health[0]
            assert "hourly_sends" in health[0]

    def test_round_robin_rotation(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.IG_ACCOUNTS = "bot1:pass1,bot2:pass2"
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            mock_settings.CHALLENGE_COOLDOWN_MINUTES = 60
            mock_settings.BLOCK_COOLDOWN_HOURS = 24
            mock_settings.MAX_CHALLENGES_BEFORE_PAUSE = 3
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._init_accounts()
            # Simulate both logged in
            for acc in svc._accounts:
                acc._logged_in = True
            first = svc._get_next_account()
            second = svc._get_next_account()
            assert first.username == "bot1"
            assert second.username == "bot2"

    def test_rotation_skips_blocked(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.IG_ACCOUNTS = "bot1:pass1,bot2:pass2"
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            mock_settings.CHALLENGE_COOLDOWN_MINUTES = 60
            mock_settings.BLOCK_COOLDOWN_HOURS = 24
            mock_settings.MAX_CHALLENGES_BEFORE_PAUSE = 3
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._init_accounts()
            svc._accounts[0]._logged_in = True
            svc._accounts[0].is_blocked = True
            svc._accounts[1]._logged_in = True
            result = svc._get_next_account()
            assert result.username == "bot2"

    def test_rotation_skips_cooldown(self):
        with patch("app.services.dm_sender_service.settings") as mock_settings:
            mock_settings.IG_SESSION_DIR = "/tmp/test_ig_sessions"
            mock_settings.IG_ACCOUNTS = "bot1:pass1,bot2:pass2"
            mock_settings.IG_USERNAME = ""
            mock_settings.IG_PASSWORD = ""
            mock_settings.CHALLENGE_COOLDOWN_MINUTES = 60
            mock_settings.BLOCK_COOLDOWN_HOURS = 24
            mock_settings.MAX_CHALLENGES_BEFORE_PAUSE = 3
            from app.services.dm_sender_service import DMSenderService
            svc = DMSenderService()
            svc._init_accounts()
            svc._accounts[0]._logged_in = True
            svc._accounts[0].last_challenge_at = datetime.now(timezone.utc)  # Just challenged
            svc._accounts[1]._logged_in = True
            result = svc._get_next_account()
            assert result.username == "bot2"


def _cryptography_available():
    import subprocess
    result = subprocess.run(
        ["python", "-c", "from cryptography.fernet import Fernet; print('ok')"],
        capture_output=True, text=True, timeout=5,
    )
    return result.returncode == 0 and "ok" in result.stdout


@pytest.mark.skipif(not _cryptography_available(), reason="cryptography package not available")
class TestSessionEncryption:
    """Test session file encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        test_file = tmp_path / "test_session.json"
        test_data = '{"pk": 12345, "session_id": "abc"}'
        test_file.write_text(test_data)

        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_SESSION_ENCRYPTION_KEY = key
            from app.services.dm_sender_service import _encrypt_file, _decrypt_file
            _encrypt_file(test_file)
            assert test_file.read_bytes() != test_data.encode()
            assert test_file.read_bytes().startswith(b"gAAAAA")
            decrypted = _decrypt_file(test_file)
            assert decrypted == test_data.encode()

    def test_no_encryption_without_key(self, tmp_path):
        test_file = tmp_path / "test_session.json"
        test_data = '{"pk": 12345}'
        test_file.write_text(test_data)

        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_SESSION_ENCRYPTION_KEY = ""
            from app.services.dm_sender_service import _encrypt_file, _decrypt_file
            _encrypt_file(test_file)
            assert test_file.read_text() == test_data
            decrypted = _decrypt_file(test_file)
            assert decrypted == test_data.encode()

    def test_decrypt_unencrypted_file(self, tmp_path):
        test_file = tmp_path / "plain.json"
        test_data = '{"pk": 99}'
        test_file.write_text(test_data)

        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        with patch("app.services.dm_sender_service.settings") as s:
            s.IG_SESSION_ENCRYPTION_KEY = key
            from app.services.dm_sender_service import _decrypt_file
            decrypted = _decrypt_file(test_file)
            assert decrypted == test_data.encode()


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
