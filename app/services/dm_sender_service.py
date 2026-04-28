import asyncio
import base64
import json
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.services.webhook_service import webhook_service

logger = logging.getLogger(__name__)

# Max send attempts before giving up on a lead
MAX_SEND_ATTEMPTS = 3

# Human-like device settings for instagrapi anti-detection
_DEVICE_PROFILES = [
    {"app_version": "269.0.0.18.75", "android_version": 31, "android_release": "12", "dpi": "480dpi", "resolution": "1080x2400", "manufacturer": "Samsung", "device": "SM-G991B", "model": "samsung"},
    {"app_version": "269.0.0.18.75", "android_version": 33, "android_release": "13", "dpi": "420dpi", "resolution": "1080x2340", "manufacturer": "Google", "device": "Pixel 7", "model": "google"},
    {"app_version": "269.0.0.18.75", "android_version": 30, "android_release": "11", "dpi": "440dpi", "resolution": "1080x2340", "manufacturer": "OnePlus", "device": "IN2025", "model": "oneplus"},
    {"app_version": "269.0.0.18.75", "android_version": 33, "android_release": "13", "dpi": "560dpi", "resolution": "1440x3200", "manufacturer": "Samsung", "device": "SM-S908B", "model": "samsung"},
    {"app_version": "269.0.0.18.75", "android_version": 32, "android_release": "12L", "dpi": "480dpi", "resolution": "1080x2400", "manufacturer": "Xiaomi", "device": "22021211RG", "model": "xiaomi"},
]


def _parse_accounts(accounts_str: str) -> list[dict]:
    """Parse IG_ACCOUNTS config: 'user:pass:proxy,user2:pass2:proxy2'"""
    if not accounts_str.strip():
        return []
    result = []
    for entry in accounts_str.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 2:
            account = {
                "username": parts[0].strip(),
                "password": parts[1].strip(),
                "proxy": ":".join(parts[2:]).strip() if len(parts) > 2 else "",
            }
            if account["username"] and account["password"]:
                result.append(account)
    return result


# --- Session encryption helpers ---

def _get_fernet():
    """Get Fernet cipher for session encryption. Returns None if key not configured."""
    key = settings.IG_SESSION_ENCRYPTION_KEY
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.warning(f"Failed to initialize Fernet encryption: {e}")
        return None


def _encrypt_file(path: Path):
    """Encrypt a file in-place using Fernet. No-op if key not configured."""
    fernet = _get_fernet()
    if not fernet or not path.exists():
        return
    try:
        data = path.read_bytes()
        # Don't re-encrypt already encrypted data
        if data.startswith(b"gAAAAA"):
            return
        encrypted = fernet.encrypt(data)
        path.write_bytes(encrypted)
        logger.debug(f"Encrypted session file: {path.name}")
    except Exception as e:
        logger.warning(f"Failed to encrypt {path.name}: {e}")


def _decrypt_file(path: Path) -> bytes | None:
    """Decrypt a file and return plaintext bytes. Returns raw bytes if not encrypted."""
    if not path.exists():
        return None
    data = path.read_bytes()
    fernet = _get_fernet()
    if fernet and data.startswith(b"gAAAAA"):
        try:
            return fernet.decrypt(data)
        except Exception as e:
            logger.warning(f"Failed to decrypt {path.name}: {e}")
            return None
    return data


class IGAccount:
    """Represents a single Instagram account with its own client and state."""

    def __init__(self, username: str, password: str, proxy: str, session_dir: Path):
        self.username = username
        self.password = password
        self.proxy = proxy
        self._client = None
        self._logged_in = False
        self._session_dir = session_dir
        self._session_dir.mkdir(parents=True, exist_ok=True)

        # Health tracking
        self.total_sent = 0
        self.total_failed = 0
        self.challenges = 0
        self.is_blocked = False
        self.created_at: datetime | None = None  # For warm-up calculation

        # Security: cooldown tracking
        self.last_challenge_at: datetime | None = None
        self.last_block_at: datetime | None = None
        self.challenges_today = 0
        self._challenges_today_date: str | None = None

        # Security: hourly rate tracking
        self._hourly_sends: list[float] = []  # timestamps of sends in current hour

        # Anti-detection: assign a consistent device profile per account
        self._device_profile = _DEVICE_PROFILES[
            hash(username) % len(_DEVICE_PROFILES)
        ]

    @property
    def session_file(self) -> Path:
        return self._session_dir / f"{self.username}_session.json"

    @property
    def health_file(self) -> Path:
        return self._session_dir / f"{self.username}_health.json"

    def is_in_cooldown(self) -> tuple[bool, str]:
        """Check if this account is in a cooldown period. Returns (is_cooling, reason)."""
        now = datetime.now(timezone.utc)

        # Challenge cooldown
        if self.last_challenge_at:
            cooldown_end = self.last_challenge_at + timedelta(minutes=settings.CHALLENGE_COOLDOWN_MINUTES)
            if now < cooldown_end:
                remaining = int((cooldown_end - now).total_seconds() / 60)
                return True, f"Challenge cooldown ({remaining}min remaining)"

        # Block cooldown
        if self.last_block_at:
            cooldown_end = self.last_block_at + timedelta(hours=settings.BLOCK_COOLDOWN_HOURS)
            if now < cooldown_end:
                remaining = int((cooldown_end - now).total_seconds() / 3600)
                return True, f"Block cooldown ({remaining}h remaining)"

        # Too many challenges today
        today = now.strftime("%Y-%m-%d")
        if self._challenges_today_date == today and self.challenges_today >= settings.MAX_CHALLENGES_BEFORE_PAUSE:
            return True, f"Too many challenges today ({self.challenges_today})"

        return False, ""

    def _check_hourly_limit(self) -> bool:
        """Check if we've hit the hourly DM limit. Returns True if OK to send."""
        now = time.time()
        one_hour_ago = now - 3600
        # Prune old entries
        self._hourly_sends = [t for t in self._hourly_sends if t > one_hour_ago]
        return len(self._hourly_sends) < settings.HOURLY_DM_LIMIT

    def _record_send(self):
        """Record a send for hourly rate tracking."""
        self._hourly_sends.append(time.time())

    def _ensure_client(self):
        if self._client is None:
            from instagrapi import Client
            self._client = Client()

            # Anti-detection: set device profile
            dp = self._device_profile
            self._client.set_device({
                "app_version": dp["app_version"],
                "android_version": dp["android_version"],
                "android_release": dp["android_release"],
                "dpi": dp["dpi"],
                "resolution": dp["resolution"],
                "manufacturer": dp["manufacturer"],
                "device": dp["device"],
                "model": dp["model"],
                "cpu": "qcom",
                "version_code": "314665256",
            })

            # Anti-detection: set realistic user agent
            self._client.set_user_agent(
                f"Instagram {dp['app_version']} Android "
                f"({dp['android_version']}/{dp['android_release']}; "
                f"{dp['dpi']}; {dp['resolution']}; "
                f"{dp['manufacturer']}; {dp['device']}; "
                f"{dp['device']}; {dp['model']}; en_US; 314665256)"
            )

            if self.proxy and not settings.IG_DISABLE_PROXIES:
                self._client.set_proxy(self.proxy)

            # Anti-detection: add random request delay
            self._client.delay_range = [2, 5]

    def _is_proxy_error(self, exc: Exception) -> bool:
        """Return True if the given exception is caused by a proxy failure."""
        msg = str(exc).lower()
        return (
            "proxyerror" in msg
            or "tunnel connection failed" in msg
            or "407 proxy" in msg
            or "unable to connect to proxy" in msg
        )

    def _disable_proxy(self, reason: str = ""):
        """Clear the proxy on this account and its live client, then recreate
        the client so the old urllib3 pool manager is fully discarded."""
        if not self.proxy and self._client is None:
            return
        logger.warning(
            f"Disabling proxy for @{self.username}"
            + (f": {reason}" if reason else "")
        )
        self.proxy = ""
        # Drop the current instagrapi client entirely — just calling
        # set_proxy(None) isn't enough because urllib3 caches the connection
        # pool. Recreating the client guarantees the next call opens a new
        # direct connection.
        self._client = None
        self._ensure_client()

    def login(self) -> bool:
        if self._logged_in:
            return True

        self._ensure_client()
        self._load_health()

        # Security: check cooldown before login attempt
        in_cooldown, reason = self.is_in_cooldown()
        if in_cooldown:
            logger.warning(f"Account @{self.username} in cooldown: {reason}")
            return False

        def _do_login() -> bool:
            # Try to restore saved session first (with decryption)
            if self.session_file.exists():
                tmp_path = self.session_file.with_suffix(".tmp")
                try:
                    decrypted = _decrypt_file(self.session_file)
                    if decrypted:
                        # Write decrypted to temp file for instagrapi to load
                        tmp_path.write_bytes(decrypted)
                        self._client.load_settings(tmp_path)
                        self._client.login(self.username, self.password)
                        # Validate session with a lightweight call
                        self._client.get_timeline_feed()
                        self._logged_in = True
                        # Re-encrypt session after successful restore
                        self._client.dump_settings(self.session_file)
                        _encrypt_file(self.session_file)
                        logger.info(f"Restored Instagram session for @{self.username}")
                        return True
                except Exception as e:
                    if self._is_proxy_error(e):
                        # Bubble up so outer handler can disable the proxy.
                        raise
                    logger.warning(
                        f"Session restore failed for @{self.username} "
                        f"({type(e).__name__}), doing fresh login"
                    )
                    self.session_file.unlink(missing_ok=True)
                finally:
                    tmp_path.unlink(missing_ok=True)

            # Fresh login
            try:
                self._client.login(self.username, self.password)
                # Save and encrypt session
                self._client.dump_settings(self.session_file)
                _encrypt_file(self.session_file)
                self._logged_in = True
                if self.created_at is None:
                    self.created_at = datetime.now(timezone.utc)
                    self._save_health()
                logger.info(f"Fresh login successful for @{self.username}")
                return True
            except Exception as e:
                if self._is_proxy_error(e):
                    raise
                error_str = str(e).lower()
                if "challenge" in error_str or "checkpoint" in error_str:
                    self._record_challenge()
                logger.error(
                    f"Instagram login failed for @{self.username}: "
                    f"{type(e).__name__}: {e}"
                )
                return False

        try:
            return _do_login()
        except Exception as e:
            if self._is_proxy_error(e):
                # Proxy leaked through validation — disable it live and retry
                # once with a direct connection. This unblocks sending even
                # when validate_proxy() passed but the real route fails.
                self._disable_proxy(reason=f"login proxy error: {type(e).__name__}")
                try:
                    return _do_login()
                except Exception as e2:
                    logger.error(
                        f"Instagram login failed for @{self.username} after "
                        f"disabling proxy: {type(e2).__name__}: {e2}"
                    )
                    return False
            logger.error(
                f"Instagram login failed for @{self.username}: "
                f"{type(e).__name__}: {e}"
            )
            return False

    def _record_challenge(self):
        """Record a challenge event for cooldown tracking."""
        now = datetime.now(timezone.utc)
        self.challenges += 1
        self.last_challenge_at = now
        today = now.strftime("%Y-%m-%d")
        if self._challenges_today_date != today:
            self._challenges_today_date = today
            self.challenges_today = 0
        self.challenges_today += 1
        self._save_health()

    def _record_block(self):
        """Record a block event for cooldown tracking."""
        self.is_blocked = True
        self.last_block_at = datetime.now(timezone.utc)
        self._save_health()

    def check_user_public(self, username: str) -> bool:
        """Pre-send check: verify target account is public and can receive DMs."""
        if not self._logged_in or not self._client:
            return False

        def _do_check() -> bool:
            # Skip the public GraphQL path (www.instagram.com) — Instagram rate-limits
            # it aggressively with 429s. Go straight to the authenticated private API
            # (i.instagram.com) which works reliably while logged in.
            user_info = self._client.user_info_by_username_v1(username)
            if user_info.is_private:
                logger.info(f"Pre-send check: @{username} is private, skipping")
                return False
            return True

        try:
            return _do_check()
        except Exception as e:
            if self._is_proxy_error(e) and self.proxy:
                # A proxy leaked through earlier validation. Kill it live so
                # the send flow isn't stuck retrying forever against a dead
                # tunnel, then re-login and retry once.
                self._disable_proxy(
                    reason=f"pre-send proxy error: {type(e).__name__}"
                )
                self._logged_in = False
                if self.login():
                    try:
                        return _do_check()
                    except Exception as e2:
                        logger.warning(
                            f"Pre-send check still failed for @{username} "
                            f"after disabling proxy: {e2}"
                        )
                        return True
            logger.warning(f"Pre-send check failed for @{username}: {e}")
            # On error, allow sending (don't block due to check failure)
            return True

    def send_dm(self, username: str, message: str) -> dict:
        if not self._logged_in:
            return {"success": False, "error": "Not logged in"}

        # Security: check hourly rate limit
        if not self._check_hourly_limit():
            return {
                "success": False,
                "error": f"Hourly DM limit reached ({settings.HOURLY_DM_LIMIT}/hour)",
                "is_rate_limited": True,
            }

        # Security: check cooldown
        in_cooldown, reason = self.is_in_cooldown()
        if in_cooldown:
            return {"success": False, "error": f"Account in cooldown: {reason}", "is_cooldown": True}

        try:
            user_id = self._client.user_id_from_username(username)

            # Anti-detection: small random pre-send delay (1-3s)
            time.sleep(random.uniform(1.0, 3.0))

            result = self._client.direct_send(message, [int(user_id)])
            self.total_sent += 1
            self._record_send()
            self._save_health()
            logger.info(f"[@{self.username}] DM sent to @{username}")
            return {"success": True, "thread_id": str(result.id) if result else None}
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"{error_type}: {e}"
            error_lower = str(e).lower()
            logger.error(f"[@{self.username}] Failed to send DM to @{username}: {error_msg}")

            is_challenge = "challenge" in error_lower or "checkpoint" in error_lower
            is_block = "block" in error_lower or "feedback_required" in error_lower
            is_not_found = "user not found" in error_lower or "user_not_found" in error_lower

            self.total_failed += 1
            if is_challenge:
                self._record_challenge()
            if is_block:
                self._record_block()

            return {
                "success": False,
                "error": error_msg[:500],
                "is_challenge": is_challenge,
                "is_block": is_block,
                "is_not_found": is_not_found,
            }

    def send_comment(self, shortcode: str, text: str) -> dict:
        """Post a comment on an Instagram post by shortcode."""
        if not self._logged_in:
            return {"success": False, "error": "Not logged in"}

        # Check hourly comment limit (separate from DM limit)
        hourly_limit = settings.HOURLY_COMMENT_LIMIT
        now = time.time()
        one_hour_ago = now - 3600
        if not hasattr(self, '_hourly_comments'):
            self._hourly_comments = []
        self._hourly_comments = [t for t in self._hourly_comments if t > one_hour_ago]
        if len(self._hourly_comments) >= hourly_limit:
            return {"success": False, "error": f"Hourly comment limit reached ({hourly_limit}/hour)", "is_rate_limited": True}

        in_cooldown, reason = self.is_in_cooldown()
        if in_cooldown:
            return {"success": False, "error": f"Account in cooldown: {reason}", "is_cooldown": True}

        try:
            from instagrapi.utils import shortcode_to_media_id
            media_id = shortcode_to_media_id(shortcode)

            # Anti-detection: pre-comment delay
            time.sleep(random.uniform(1.5, 4.0))

            self._client.media_comment(media_id, text)
            self._hourly_comments.append(time.time())
            self.total_sent += 1
            self._save_health()
            logger.info(f"[@{self.username}] Comment posted on post {shortcode}")
            return {"success": True}
        except ImportError:
            # Fallback: try media_pk_from_code
            try:
                media_pk = self._client.media_pk_from_code(shortcode)
                time.sleep(random.uniform(1.5, 4.0))
                self._client.media_comment(media_pk, text)
                self._hourly_comments.append(time.time())
                self.total_sent += 1
                self._save_health()
                logger.info(f"[@{self.username}] Comment posted on post {shortcode} (fallback)")
                return {"success": True}
            except Exception as e2:
                error_msg = f"{type(e2).__name__}: {e2}"
                logger.error(f"[@{self.username}] Comment failed on {shortcode}: {error_msg}")
                self.total_failed += 1
                return {"success": False, "error": error_msg[:500]}
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"{error_type}: {e}"
            error_lower = str(e).lower()
            logger.error(f"[@{self.username}] Comment failed on {shortcode}: {error_msg}")

            is_challenge = "challenge" in error_lower or "checkpoint" in error_lower
            is_block = "block" in error_lower or "feedback_required" in error_lower

            self.total_failed += 1
            if is_challenge:
                self._record_challenge()
            if is_block:
                self._record_block()

            return {
                "success": False,
                "error": error_msg[:500],
                "is_challenge": is_challenge,
                "is_block": is_block,
            }

    def save_session(self):
        if self._client and self._logged_in:
            try:
                self._client.dump_settings(self.session_file)
                _encrypt_file(self.session_file)
            except Exception as e:
                logger.warning(f"Failed to save session for @{self.username}: {e}")
        self._save_health()

    def get_warmup_limit(self) -> int:
        """Calculate daily limit based on account age (warm-up period)."""
        if self.created_at is None:
            return settings.IG_WARMUP_START_LIMIT

        days_active = (datetime.now(timezone.utc) - self.created_at).days
        warmup_days = settings.IG_WARMUP_DAYS
        start_limit = settings.IG_WARMUP_START_LIMIT
        full_limit = settings.DAILY_DM_LIMIT

        if days_active >= warmup_days:
            return full_limit

        # Linear ramp from start_limit to full_limit over warmup_days
        progress = days_active / warmup_days
        return int(start_limit + (full_limit - start_limit) * progress)

    def get_health(self) -> dict:
        """Return health metrics for this account."""
        total = self.total_sent + self.total_failed
        success_rate = (self.total_sent / total * 100) if total > 0 else 100.0
        in_cooldown, cooldown_reason = self.is_in_cooldown()
        return {
            "username": self.username,
            "logged_in": self._logged_in,
            "is_blocked": self.is_blocked,
            "in_cooldown": in_cooldown,
            "cooldown_reason": cooldown_reason,
            "total_sent": self.total_sent,
            "total_failed": self.total_failed,
            "challenges": self.challenges,
            "challenges_today": self.challenges_today,
            "success_rate": round(success_rate, 1),
            "warmup_limit": self.get_warmup_limit(),
            "hourly_sends": len(self._hourly_sends),
            "hourly_limit": settings.HOURLY_DM_LIMIT,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def _save_health(self):
        try:
            data = {
                "total_sent": self.total_sent,
                "total_failed": self.total_failed,
                "challenges": self.challenges,
                "is_blocked": self.is_blocked,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "last_challenge_at": self.last_challenge_at.isoformat() if self.last_challenge_at else None,
                "last_block_at": self.last_block_at.isoformat() if self.last_block_at else None,
                "challenges_today": self.challenges_today,
                "challenges_today_date": self._challenges_today_date,
            }
            # Health file is also encrypted if key is available
            raw = json.dumps(data).encode()
            fernet = _get_fernet()
            if fernet:
                raw = fernet.encrypt(raw)
            self.health_file.write_bytes(raw)
        except Exception:
            pass

    def _load_health(self):
        if self.health_file.exists():
            try:
                raw = _decrypt_file(self.health_file)
                if raw is None:
                    return
                data = json.loads(raw)
                self.total_sent = data.get("total_sent", 0)
                self.total_failed = data.get("total_failed", 0)
                self.challenges = data.get("challenges", 0)
                self.is_blocked = data.get("is_blocked", False)
                if data.get("created_at"):
                    self.created_at = datetime.fromisoformat(data["created_at"])
                if data.get("last_challenge_at"):
                    self.last_challenge_at = datetime.fromisoformat(data["last_challenge_at"])
                if data.get("last_block_at"):
                    self.last_block_at = datetime.fromisoformat(data["last_block_at"])
                self.challenges_today = data.get("challenges_today", 0)
                self._challenges_today_date = data.get("challenges_today_date")
            except Exception as e:
                logger.warning(f"Failed to load health data for @{self.username}: {type(e).__name__}: {e}")

    def validate_proxy(self) -> bool:
        """Validate that the proxy is reachable before using it for sends.

        Tests the proxy against Instagram itself, not a generic site like
        httpbin.org — a proxy can work for generic sites but still fail to
        reach Instagram (e.g. 407 Proxy Authentication Required when
        tunneling to i.instagram.com).
        """
        if not self.proxy:
            return True  # No proxy configured, OK
        try:
            import httpx
            with httpx.Client(proxy=self.proxy, timeout=10) as client:
                # Use Instagram's own favicon — always 200, no auth needed,
                # routes through the same CONNECT tunnel as real API calls.
                resp = client.get("https://www.instagram.com/favicon.ico")
                if resp.status_code < 400:
                    logger.info(f"Proxy validated for @{self.username} against Instagram")
                    return True
                logger.warning(
                    f"Proxy for @{self.username} returned HTTP {resp.status_code} "
                    f"when reaching Instagram"
                )
                return False
        except Exception as e:
            logger.warning(f"Proxy validation failed for @{self.username}: {e}")
            return False


class DMSenderService:
    """Send Instagram DMs via instagrapi with multi-account rotation, warm-up, and rate limiting."""

    def __init__(self):
        self._session_path = Path(settings.IG_SESSION_DIR)
        self._session_path.mkdir(parents=True, exist_ok=True)
        self._accounts: list[IGAccount] = []
        self._current_account_idx = 0

    def _init_accounts(self):
        """Initialize accounts from config (DB, ig_config.json, multi-account env, or single)."""
        if self._accounts:
            return

        # Try database first (set via Accounts & Proxies UI)
        try:
            self._load_accounts_from_db()
            if self._accounts:
                return
        except Exception as e:
            logger.debug(f"DB config not available: {e}")

        disable_proxies = settings.IG_DISABLE_PROXIES

        # Fallback: ig_config.json (legacy)
        config_path = Path("ig_config.json")
        if config_path.exists():
            try:
                import json
                data = json.loads(config_path.read_text(encoding="utf-8"))
                cfg_accounts = data.get("accounts", [])
                if cfg_accounts:
                    for acc in cfg_accounts:
                        proxy = "" if disable_proxies else acc.get("proxy", "")
                        self._accounts.append(IGAccount(
                            username=acc["username"],
                            password=acc["password"],
                            proxy=proxy,
                            session_dir=self._session_path,
                        ))
                    logger.info(f"Configured {len(self._accounts)} IG accounts from ig_config.json")
                    return
            except Exception as e:
                logger.warning(f"Failed to read ig_config.json: {e}")

        # Try multi-account config first
        multi = _parse_accounts(settings.IG_ACCOUNTS)
        if multi:
            for acc in multi:
                proxy = "" if disable_proxies else acc["proxy"]
                self._accounts.append(IGAccount(
                    username=acc["username"],
                    password=acc["password"],
                    proxy=proxy,
                    session_dir=self._session_path,
                ))
            logger.info(f"Configured {len(self._accounts)} IG accounts for rotation")
        elif settings.IG_USERNAME and settings.IG_PASSWORD:
            # Fallback to single account
            proxy = "" if disable_proxies else settings.PROXY_URL
            self._accounts.append(IGAccount(
                username=settings.IG_USERNAME,
                password=settings.IG_PASSWORD,
                proxy=proxy,
                session_dir=self._session_path,
            ))
            logger.info("Configured 1 IG account (single mode)")

    def _load_accounts_from_db(self):
        """Load IG accounts from the system_config table in the database."""
        import json
        import asyncio

        async def _read():
            from sqlalchemy import text
            from app.database import create_worker_session

            async with create_worker_session()() as db:
                result = await db.execute(
                    text("SELECT value FROM public.system_config WHERE key = :k"),
                    {"k": "ig_config"},
                )
                row = result.scalar_one_or_none()
                if not row:
                    return None
                return json.loads(row)

        # Run async query in a new event loop (called from sync context)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context, use a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    data = pool.submit(lambda: asyncio.run(_read())).result(timeout=10)
            else:
                data = loop.run_until_complete(_read())
        except RuntimeError:
            data = asyncio.run(_read())

        if not data:
            return

        cfg_accounts = data.get("accounts", [])
        disable_proxies = settings.IG_DISABLE_PROXIES
        for acc in cfg_accounts:
            proxy = "" if disable_proxies else acc.get("proxy", "")
            self._accounts.append(IGAccount(
                username=acc["username"],
                password=acc["password"],
                proxy=proxy,
                session_dir=self._session_path,
            ))
        if self._accounts:
            if disable_proxies:
                logger.info(
                    f"Configured {len(self._accounts)} IG accounts from database "
                    f"(proxies disabled via IG_DISABLE_PROXIES)"
                )
            else:
                logger.info(f"Configured {len(self._accounts)} IG accounts from database")

    def login(self) -> bool:
        """Login all configured accounts. Returns True if at least one succeeds."""
        self._init_accounts()

        if not self._accounts:
            logger.error("No IG accounts configured (set IG_USERNAME/IG_PASSWORD or IG_ACCOUNTS)")
            return False

        # Security: validate proxies before login. If a proxy fails, actually
        # clear it on the account so _ensure_client() won't re-apply it and
        # subsequent Instagram API calls don't keep tunneling through a broken
        # proxy (which was causing 407 Proxy Authentication Required errors).
        for acc in self._accounts:
            if acc.proxy and not acc.validate_proxy():
                logger.warning(
                    f"Proxy failed for @{acc.username}, proceeding without proxy"
                )
                acc.proxy = ""
                # If the instagrapi client was already instantiated, reset its
                # proxy too so the broken one is removed from the live session.
                if acc._client is not None:
                    try:
                        acc._client.set_proxy(None)
                    except Exception:
                        pass

        success_count = 0
        for acc in self._accounts:
            # Skip blocked or cooling-down accounts
            in_cooldown, reason = acc.is_in_cooldown()
            if acc.is_blocked and in_cooldown:
                logger.warning(f"Skipping account @{acc.username}: {reason}")
                continue
            if acc.login():
                success_count += 1

        if success_count == 0:
            logger.error("All IG account logins failed")
            return False

        logger.info(f"Logged in to {success_count}/{len(self._accounts)} accounts")
        return True

    def _get_next_account(self, allowed_usernames: list[str] | None = None) -> IGAccount | None:
        """Round-robin select next available (logged in, not blocked, not in cooldown) account.

        If ``allowed_usernames`` is provided, only accounts whose username is in the
        list are considered. An empty list or ``None`` means "any account".
        """
        if not self._accounts:
            return None

        allowed_set = {u.lower() for u in allowed_usernames} if allowed_usernames else None

        for _ in range(len(self._accounts)):
            acc = self._accounts[self._current_account_idx]
            self._current_account_idx = (self._current_account_idx + 1) % len(self._accounts)
            if allowed_set is not None and acc.username.lower() not in allowed_set:
                continue
            if acc._logged_in and not acc.is_blocked:
                in_cooldown, _ = acc.is_in_cooldown()
                if not in_cooldown:
                    return acc

        return None

    def send_dm(self, username: str, message: str, allowed_usernames: list[str] | None = None) -> dict:
        """Send a DM using the next available account.

        If ``allowed_usernames`` is given, only those accounts are eligible.
        """
        account = self._get_next_account(allowed_usernames=allowed_usernames)
        if not account:
            if allowed_usernames:
                return {
                    "success": False,
                    "error": f"No available IG accounts in allowed list {allowed_usernames} (all blocked/cooldown/not logged in)",
                }
            return {"success": False, "error": "No available IG accounts (all blocked/cooldown)"}
        return account.send_dm(username, message)

    def send_comment(self, shortcode: str, text: str) -> dict:
        """Send a comment using the next available account."""
        account = self._get_next_account()
        if not account:
            return {"success": False, "error": "No available IG accounts (all blocked/cooldown)"}
        return account.send_comment(shortcode, text)

    async def get_daily_comment_count(self, db: AsyncSession) -> int:
        """Count comments sent today for rate limiting."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.comment_status == "sent",
                Lead.comment_sent_at >= today_start,
            )
        )
        return result.scalar() or 0

    async def send_campaign_comments(
        self,
        campaign_id: str,
        db: AsyncSession,
        lead_ids: list[str] | None = None,
        progress_callback=None,
    ) -> dict:
        """Send comments for a campaign with rate limiting and delays.

        If lead_ids is provided, only send to those specific leads (single send).
        Otherwise, send to all pending leads (bulk send).
        """
        daily_count = await self.get_daily_comment_count(db)
        daily_limit = settings.DAILY_COMMENT_LIMIT

        if daily_count >= daily_limit:
            logger.warning(f"Daily comment limit reached ({daily_count}/{daily_limit})")
            return {
                "sent_count": 0, "failed_count": 0, "skipped_count": 0,
                "paused": True, "reason": f"Limite diario alcanzado ({daily_count}/{daily_limit})",
            }

        remaining_today = daily_limit - daily_count

        if lead_ids:
            # Single or specific leads
            result = await db.execute(
                select(Lead).where(
                    Lead.id.in_(lead_ids),
                    Lead.comment_status == "pending",
                    Lead.comment_message.isnot(None),
                    Lead.commented_post_shortcode.isnot(None),
                )
            )
        else:
            # Bulk: all pending comments for campaign
            result = await db.execute(
                select(Lead).where(
                    Lead.campaign_id == campaign_id,
                    Lead.comment_status == "pending",
                    Lead.comment_message.isnot(None),
                    Lead.commented_post_shortcode.isnot(None),
                    Lead.comment_attempts < 3,
                    Lead.ig_is_private.is_not(True),
                ).order_by(Lead.score.desc()).limit(remaining_today)
            )

        leads = list(result.scalars().all())

        if not leads:
            return {"sent_count": 0, "failed_count": 0, "skipped_count": 0, "paused": False, "reason": "No hay comentarios pendientes"}

        logger.info(f"Sending {len(leads)} comments (daily: {daily_count}/{daily_limit})")

        sent_count = 0
        failed_count = 0
        skipped_count = 0

        for i, lead in enumerate(leads):
            # Pre-send public check
            if settings.PRE_SEND_CHECK_PUBLIC:
                if not self.pre_send_check(lead.ig_username):
                    lead.comment_status = "skipped"
                    lead.ig_is_private = True
                    skipped_count += 1
                    await db.commit()
                    continue

            # Select variant
            if lead.comment_variant_used:
                variant = "B" if lead.comment_variant_used == "A" else "A"
            else:
                variant = random.choice(["A", "B"]) if lead.comment_variant_b else "A"

            comment_text = lead.comment_message if variant == "A" else (lead.comment_variant_b or lead.comment_message)
            lead.comment_variant_used = variant

            result = self.send_comment(lead.commented_post_shortcode, comment_text)

            if result["success"]:
                lead.comment_status = "sent"
                lead.comment_sent_at = datetime.now(timezone.utc)
                sent_count += 1
            elif result.get("is_rate_limited") or result.get("is_cooldown"):
                # Stop sending, save progress
                await db.commit()
                self.save_sessions()
                return {
                    "sent_count": sent_count, "failed_count": failed_count, "skipped_count": skipped_count,
                    "paused": True, "reason": result["error"],
                }
            else:
                lead.comment_attempts += 1
                lead.comment_error = result.get("error", "Unknown error")
                if lead.comment_attempts >= 3:
                    lead.comment_status = "failed"
                failed_count += 1

            await db.commit()

            if progress_callback:
                try:
                    cb_result = progress_callback(i + 1, len(leads), lead.ig_username, result["success"])
                    # Support both sync and async callbacks
                    if asyncio.iscoroutine(cb_result):
                        await cb_result
                except Exception:
                    pass

            # Human-like delay between comments
            if i < len(leads) - 1:
                delay = random.uniform(settings.COMMENT_DELAY_MIN, settings.COMMENT_DELAY_MAX)
                if not result["success"]:
                    delay *= 1.5
                delay += random.uniform(-10, 10)
                delay = max(30, delay)
                logger.info(f"Waiting {delay:.0f}s before next comment...")
                time.sleep(delay)

        self.save_sessions()
        return {
            "sent_count": sent_count, "failed_count": failed_count, "skipped_count": skipped_count,
            "paused": False, "reason": f"Completado: {sent_count} enviados, {failed_count} fallidos, {skipped_count} omitidos",
        }

    def pre_send_check(self, username: str) -> bool:
        """Check if target account is public before sending. Uses first available account."""
        if not settings.PRE_SEND_CHECK_PUBLIC:
            return True
        account = self._get_next_account()
        if not account:
            return True  # No account to check, don't block
        return account.check_user_public(username)

    def save_sessions(self):
        """Persist all account sessions to disk (encrypted)."""
        for acc in self._accounts:
            acc.save_session()

    def get_accounts_health(self) -> list[dict]:
        """Return health metrics for all accounts."""
        self._init_accounts()
        return [acc.get_health() for acc in self._accounts]

    async def get_daily_send_count(self, db: AsyncSession) -> int:
        """Count DMs sent today for rate limiting."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.status == "sent",
                Lead.sent_at >= today_start,
            )
        )
        return result.scalar() or 0

    def _get_effective_daily_limit(self) -> int:
        """Calculate daily limit considering warm-up across all accounts."""
        if not self._accounts:
            return settings.DAILY_DM_LIMIT

        # Total limit is the sum of each account's warm-up limit
        total = sum(
            acc.get_warmup_limit()
            for acc in self._accounts
            if acc._logged_in and not acc.is_blocked
        )
        return total if total > 0 else settings.DAILY_DM_LIMIT

    async def get_next_leads_to_send(
        self, campaign_id: str, db: AsyncSession, limit: int = 10
    ) -> list[Lead]:
        """Get next batch of leads ready to send, ordered by score DESC.
        Only returns public accounts (ig_is_private != True).
        """
        result = await db.execute(
            select(Lead).where(
                Lead.campaign_id == campaign_id,
                Lead.status.in_(["dm_ready", "retry"]),
                Lead.send_attempts < MAX_SEND_ATTEMPTS,
                Lead.ig_is_private.is_not(True),  # Security: only public accounts
            ).order_by(Lead.score.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def send_campaign_dms(
        self,
        campaign_id: str,
        db: AsyncSession,
        progress_callback=None,
    ) -> dict:
        """Send DMs for a campaign with rate limiting, warm-up, and random delays.

        Returns dict with sent_count, failed_count, skipped_count, paused (bool), reason.
        """
        # Sending schedule check — only send during configured hours
        from app.models.campaign import Campaign
        campaign_result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign_obj = campaign_result.scalar_one_or_none()
        campaign_settings = (campaign_obj.settings or {}) if campaign_obj else {}

        sending_start = campaign_settings.get("sending_hours_start", "")
        sending_end = campaign_settings.get("sending_hours_end", "")
        sending_tz = campaign_settings.get("sending_timezone", "")

        if sending_start and sending_end and sending_tz:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(sending_tz)
                now_local = datetime.now(tz)
                start_h, start_m = map(int, sending_start.split(":"))
                end_h, end_m = map(int, sending_end.split(":"))
                current_minutes = now_local.hour * 60 + now_local.minute
                start_minutes = start_h * 60 + start_m
                end_minutes = end_h * 60 + end_m

                if start_minutes <= end_minutes:
                    outside_hours = current_minutes < start_minutes or current_minutes >= end_minutes
                else:
                    # Overnight schedule (e.g., 22:00-06:00): outside = before start AND after/at end
                    outside_hours = current_minutes < start_minutes and current_minutes >= end_minutes

                if outside_hours:
                    logger.info(
                        f"Outside sending hours for campaign {campaign_id}: "
                        f"{now_local.strftime('%H:%M')} not in {sending_start}-{sending_end} ({sending_tz})"
                    )
                    return {
                        "sent_count": 0,
                        "failed_count": 0,
                        "skipped_count": 0,
                        "paused": True,
                        "reason": f"Outside sending hours ({sending_start}-{sending_end} {sending_tz})",
                    }
            except Exception as e:
                logger.warning(f"Failed to check sending schedule: {e}")

        # Per-campaign account whitelist: only use these IG accounts for sending.
        # Empty list or missing key = rotate through all configured accounts.
        raw_allowed = campaign_settings.get("ig_accounts") or []
        allowed_usernames = [u.strip() for u in raw_allowed if isinstance(u, str) and u.strip()]
        if allowed_usernames:
            available_usernames = {a.username.lower() for a in self._accounts}
            missing = [u for u in allowed_usernames if u.lower() not in available_usernames]
            if missing:
                logger.warning(
                    f"Campaign {campaign_id} requests accounts not configured: {missing} "
                    f"(available: {sorted(available_usernames)})"
                )
            # Keep only the ones that actually exist
            allowed_usernames = [u for u in allowed_usernames if u.lower() in available_usernames]
            if not allowed_usernames:
                return {
                    "sent_count": 0, "failed_count": 0, "skipped_count": 0,
                    "paused": True,
                    "reason": f"None of the campaign's assigned accounts are configured: {raw_allowed}",
                }
            logger.info(f"Campaign {campaign_id} restricted to accounts: {allowed_usernames}")

        daily_count = await self.get_daily_send_count(db)
        daily_limit = self._get_effective_daily_limit()

        if daily_count >= daily_limit:
            logger.warning(f"Daily DM limit reached ({daily_count}/{daily_limit})")
            return {
                "sent_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "paused": True,
                "reason": f"Daily limit reached ({daily_count}/{daily_limit})",
            }

        remaining_today = daily_limit - daily_count
        leads = await self.get_next_leads_to_send(campaign_id, db, limit=remaining_today)

        if not leads:
            logger.info(f"No leads ready to send for campaign {campaign_id}")
            return {"sent_count": 0, "failed_count": 0, "skipped_count": 0, "paused": False, "reason": "No leads to send"}

        logger.info(f"Sending DMs to {len(leads)} leads (daily: {daily_count}/{daily_limit})")

        sent_count = 0
        failed_count = 0
        skipped_count = 0

        for i, lead in enumerate(leads):
            # Security: pre-send check that account is public
            if settings.PRE_SEND_CHECK_PUBLIC:
                if not self.pre_send_check(lead.ig_username):
                    lead.status = "failed"
                    lead.send_error = "Target account is private"
                    lead.delivery_status = "skipped_private"
                    lead.ig_is_private = True  # Update for future filtering
                    await db.commit()
                    skipped_count += 1
                    logger.info(f"Skipped @{lead.ig_username}: private account (pre-send check)")
                    continue

            # Pick DM variant: A/B test random assignment or fallback logic
            if lead.dm_variant_used in ("A", "B") and lead.send_attempts > 0:
                # Retry: switch to the other variant if available
                if lead.dm_variant_used == "A" and lead.dm_variant_b:
                    message = lead.dm_variant_b
                    variant = "B"
                elif lead.dm_variant_used == "B" and lead.dm_message:
                    message = lead.dm_message
                    variant = "A"
                else:
                    message = lead.dm_message or lead.dm_variant_b
                    variant = "A" if lead.dm_message else "B"
            elif settings.AB_TEST_ENABLED and lead.dm_variant_b:
                # A/B test: randomly assign based on split ratio
                if random.random() < settings.AB_TEST_SPLIT:
                    message = lead.dm_message
                    variant = "A"
                else:
                    message = lead.dm_variant_b
                    variant = "B"
            else:
                message = lead.dm_message
                variant = "A"

            if not message:
                logger.warning(f"No DM message for @{lead.ig_username}, skipping")
                lead.status = "failed"
                lead.send_error = "No DM message available"
                failed_count += 1
                continue

            # Mark as sending
            lead.status = "sending"
            lead.dm_variant_used = variant
            await db.commit()

            # Send the DM (uses round-robin account rotation, filtered by
            # campaign.settings.ig_accounts if configured)
            result = self.send_dm(lead.ig_username, message, allowed_usernames=allowed_usernames or None)

            if result["success"]:
                lead.status = "sent"
                lead.sent_at = datetime.now(timezone.utc)
                lead.delivery_status = "sent"
                lead.send_error = None
                sent_count += 1
                logger.info(f"Sent DM ({variant}) to @{lead.ig_username} [{sent_count}/{len(leads)}]")

                # CRM: auto-classify stage to "contacted"
                try:
                    from app.services.crm_service import crm_service
                    await crm_service.auto_classify_stage(str(lead.id), db, event="dm_sent")
                except Exception:
                    pass

                # Trigger webhook for successful DM send
                try:
                    await webhook_service.trigger_event(
                        client_id=str(lead.client_id),
                        event_type="dm.sent",
                        payload={
                            "lead_id": str(lead.id),
                            "ig_username": lead.ig_username,
                            "campaign_id": str(lead.campaign_id),
                            "variant": variant,
                        },
                        db=db,
                    )
                except Exception:
                    pass
            else:
                lead.send_attempts += 1
                lead.send_error = result.get("error", "Unknown error")

                # Rate limited → pause without counting as failure
                if result.get("is_rate_limited") or result.get("is_cooldown"):
                    lead.status = "retry"
                    lead.delivery_status = "rate_limited"
                    await db.commit()
                    return {
                        "sent_count": sent_count,
                        "failed_count": failed_count,
                        "skipped_count": skipped_count,
                        "paused": True,
                        "reason": result.get("error", "Rate limited"),
                    }

                # User not found → mark as failed immediately
                if result.get("is_not_found"):
                    lead.status = "failed"
                    lead.delivery_status = "user_not_found"
                    failed_count += 1
                    await db.commit()
                    continue

                # Challenge or block → pause the whole campaign
                if result.get("is_challenge") or result.get("is_block"):
                    lead.status = "retry"
                    lead.delivery_status = "challenge" if result.get("is_challenge") else "blocked"
                    await db.commit()

                    # Check if ANY account (in the campaign's whitelist, if any) is still usable
                    usable = self._get_next_account(allowed_usernames=allowed_usernames or None)
                    if usable is None:
                        reason = "All accounts challenged/blocked — waiting for cooldown"
                        logger.warning(f"Pausing campaign: {reason}")
                        return {
                            "sent_count": sent_count,
                            "failed_count": failed_count,
                            "skipped_count": skipped_count,
                            "paused": True,
                            "reason": reason,
                        }
                    else:
                        # Just skip this lead, continue with next account
                        logger.warning(f"Account hit challenge, rotating to @{usable.username}")
                        continue

                if lead.send_attempts >= MAX_SEND_ATTEMPTS:
                    lead.status = "failed"
                    lead.delivery_status = "max_attempts"
                    failed_count += 1

                    # Trigger webhook for failed DM
                    try:
                        await webhook_service.trigger_event(
                            client_id=str(lead.client_id),
                            event_type="dm.failed",
                            payload={
                                "lead_id": str(lead.id),
                                "ig_username": lead.ig_username,
                                "campaign_id": str(lead.campaign_id),
                                "error": lead.send_error,
                                "send_attempts": lead.send_attempts,
                            },
                            db=db,
                        )
                    except Exception:
                        pass
                else:
                    lead.status = "retry"
                    lead.delivery_status = "retry"

            await db.commit()

            if progress_callback:
                try:
                    cb_result = progress_callback(i + 1, len(leads), lead.ig_username, result["success"])
                    # Support both sync and async callbacks
                    if asyncio.iscoroutine(cb_result):
                        await cb_result
                except Exception:
                    pass

            # Human-like delay between sends (skip after last one)
            if i < len(leads) - 1:
                # Variable delay: shorter for successful sends, longer after failures
                base_min = settings.DM_DELAY_MIN
                base_max = settings.DM_DELAY_MAX
                if not result["success"]:
                    # After failure, wait longer (1.5x-2x)
                    base_min = int(base_min * 1.5)
                    base_max = int(base_max * 2)
                delay = random.uniform(base_min, base_max)
                # Add small random jitter for more human-like behavior
                delay += random.uniform(-5, 10)
                delay = max(15, delay)  # Minimum 15s between any sends
                logger.debug(f"Waiting {delay:.1f}s before next DM")
                await asyncio.sleep(delay)

        self.save_sessions()

        return {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "paused": False,
            "reason": "Batch complete",
        }


dm_sender_service = DMSenderService()
