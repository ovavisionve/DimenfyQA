import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead

logger = logging.getLogger(__name__)

# Max send attempts before giving up on a lead
MAX_SEND_ATTEMPTS = 3


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

    @property
    def session_file(self) -> Path:
        return self._session_dir / f"{self.username}_session.json"

    @property
    def health_file(self) -> Path:
        return self._session_dir / f"{self.username}_health.json"

    def _ensure_client(self):
        if self._client is None:
            from instagrapi import Client
            self._client = Client()
            if self.proxy:
                self._client.set_proxy(self.proxy)

    def login(self) -> bool:
        if self._logged_in:
            return True

        self._ensure_client()
        self._load_health()

        # Try to restore saved session first
        if self.session_file.exists():
            try:
                self._client.load_settings(self.session_file)
                self._client.login(self.username, self.password)
                self._client.get_timeline_feed()
                self._logged_in = True
                logger.info(f"Restored Instagram session for @{self.username}")
                return True
            except Exception as e:
                logger.warning(f"Session restore failed for @{self.username} ({type(e).__name__}), doing fresh login")
                self.session_file.unlink(missing_ok=True)

        # Fresh login
        try:
            self._client.login(self.username, self.password)
            self._client.dump_settings(self.session_file)
            self._logged_in = True
            if self.created_at is None:
                self.created_at = datetime.now(timezone.utc)
                self._save_health()
            logger.info(f"Fresh login successful for @{self.username}")
            return True
        except Exception as e:
            logger.error(f"Instagram login failed for @{self.username}: {type(e).__name__}: {e}")
            return False

    def send_dm(self, username: str, message: str) -> dict:
        if not self._logged_in:
            return {"success": False, "error": "Not logged in"}

        try:
            user_id = self._client.user_id_from_username(username)
            result = self._client.direct_send(message, [int(user_id)])
            self.total_sent += 1
            logger.info(f"[@{self.username}] DM sent to @{username}")
            return {"success": True, "thread_id": str(result.id) if result else None}
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"{error_type}: {e}"
            logger.error(f"[@{self.username}] Failed to send DM to @{username}: {error_msg}")

            is_challenge = "challenge" in str(e).lower() or "checkpoint" in str(e).lower()
            is_block = "block" in str(e).lower() or "feedback_required" in str(e).lower()

            self.total_failed += 1
            if is_challenge:
                self.challenges += 1
            if is_block:
                self.is_blocked = True

            self._save_health()

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
        return {
            "username": self.username,
            "logged_in": self._logged_in,
            "is_blocked": self.is_blocked,
            "total_sent": self.total_sent,
            "total_failed": self.total_failed,
            "challenges": self.challenges,
            "success_rate": round(success_rate, 1),
            "warmup_limit": self.get_warmup_limit(),
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
            }
            self.health_file.write_text(json.dumps(data))
        except Exception:
            pass

    def _load_health(self):
        if self.health_file.exists():
            try:
                data = json.loads(self.health_file.read_text())
                self.total_sent = data.get("total_sent", 0)
                self.total_failed = data.get("total_failed", 0)
                self.challenges = data.get("challenges", 0)
                self.is_blocked = data.get("is_blocked", False)
                if data.get("created_at"):
                    self.created_at = datetime.fromisoformat(data["created_at"])
            except Exception:
                pass


class DMSenderService:
    """Send Instagram DMs via instagrapi with multi-account rotation, warm-up, and rate limiting."""

    def __init__(self):
        self._session_path = Path(settings.IG_SESSION_DIR)
        self._session_path.mkdir(parents=True, exist_ok=True)
        self._accounts: list[IGAccount] = []
        self._current_account_idx = 0

    def _init_accounts(self):
        """Initialize accounts from config (multi-account or single)."""
        if self._accounts:
            return

        # Try multi-account config first
        multi = _parse_accounts(settings.IG_ACCOUNTS)
        if multi:
            for acc in multi:
                self._accounts.append(IGAccount(
                    username=acc["username"],
                    password=acc["password"],
                    proxy=acc["proxy"],
                    session_dir=self._session_path,
                ))
            logger.info(f"Configured {len(self._accounts)} IG accounts for rotation")
        elif settings.IG_USERNAME and settings.IG_PASSWORD:
            # Fallback to single account
            self._accounts.append(IGAccount(
                username=settings.IG_USERNAME,
                password=settings.IG_PASSWORD,
                proxy=settings.PROXY_URL,
                session_dir=self._session_path,
            ))
            logger.info("Configured 1 IG account (single mode)")

    def login(self) -> bool:
        """Login all configured accounts. Returns True if at least one succeeds."""
        self._init_accounts()

        if not self._accounts:
            logger.error("No IG accounts configured (set IG_USERNAME/IG_PASSWORD or IG_ACCOUNTS)")
            return False

        success_count = 0
        for acc in self._accounts:
            if acc.is_blocked:
                logger.warning(f"Skipping blocked account @{acc.username}")
                continue
            if acc.login():
                success_count += 1

        if success_count == 0:
            logger.error("All IG account logins failed")
            return False

        logger.info(f"Logged in to {success_count}/{len(self._accounts)} accounts")
        return True

    def _get_next_account(self) -> IGAccount | None:
        """Round-robin select next available (logged in, not blocked) account."""
        if not self._accounts:
            return None

        for _ in range(len(self._accounts)):
            acc = self._accounts[self._current_account_idx]
            self._current_account_idx = (self._current_account_idx + 1) % len(self._accounts)
            if acc._logged_in and not acc.is_blocked:
                return acc

        return None

    def send_dm(self, username: str, message: str) -> dict:
        """Send a DM using the next available account."""
        account = self._get_next_account()
        if not account:
            return {"success": False, "error": "No available IG accounts"}
        return account.send_dm(username, message)

    def save_sessions(self):
        """Persist all account sessions to disk."""
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
        total = sum(acc.get_warmup_limit() for acc in self._accounts if acc._logged_in and not acc.is_blocked)
        return total if total > 0 else settings.DAILY_DM_LIMIT

    async def get_next_leads_to_send(
        self, campaign_id: str, db: AsyncSession, limit: int = 10
    ) -> list[Lead]:
        """Get next batch of leads ready to send, ordered by score DESC."""
        result = await db.execute(
            select(Lead).where(
                Lead.campaign_id == campaign_id,
                Lead.status.in_(["dm_ready", "retry"]),
                Lead.send_attempts < MAX_SEND_ATTEMPTS,
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

        Returns dict with sent_count, failed_count, paused (bool), reason.
        """
        daily_count = await self.get_daily_send_count(db)
        daily_limit = self._get_effective_daily_limit()

        if daily_count >= daily_limit:
            logger.warning(f"Daily DM limit reached ({daily_count}/{daily_limit})")
            return {
                "sent_count": 0,
                "failed_count": 0,
                "paused": True,
                "reason": f"Daily limit reached ({daily_count}/{daily_limit})",
            }

        remaining_today = daily_limit - daily_count
        leads = await self.get_next_leads_to_send(campaign_id, db, limit=remaining_today)

        if not leads:
            logger.info(f"No leads ready to send for campaign {campaign_id}")
            return {"sent_count": 0, "failed_count": 0, "paused": False, "reason": "No leads to send"}

        logger.info(f"Sending DMs to {len(leads)} leads (daily: {daily_count}/{daily_limit})")

        sent_count = 0
        failed_count = 0

        for i, lead in enumerate(leads):
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

            # Send the DM (uses round-robin account rotation)
            result = self.send_dm(lead.ig_username, message)

            if result["success"]:
                lead.status = "sent"
                lead.sent_at = datetime.now(timezone.utc)
                lead.delivery_status = "sent"
                lead.send_error = None
                sent_count += 1
                logger.info(f"Sent DM ({variant}) to @{lead.ig_username} [{sent_count}/{len(leads)}]")
            else:
                lead.send_attempts += 1
                lead.send_error = result.get("error", "Unknown error")

                # Challenge or block → pause the whole campaign
                if result.get("is_challenge") or result.get("is_block"):
                    lead.status = "retry"
                    lead.delivery_status = "challenge" if result.get("is_challenge") else "blocked"
                    await db.commit()

                    # Check if ANY account is still usable
                    usable = self._get_next_account()
                    if usable is None:
                        reason = "All accounts challenged/blocked"
                        logger.warning(f"Pausing campaign: {reason}")
                        return {
                            "sent_count": sent_count,
                            "failed_count": failed_count,
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
                else:
                    lead.status = "retry"
                    lead.delivery_status = "retry"

            await db.commit()

            if progress_callback:
                try:
                    progress_callback(i + 1, len(leads), lead.ig_username, result["success"])
                except Exception:
                    pass

            # Random delay between sends (skip after last one)
            if i < len(leads) - 1:
                delay = random.uniform(settings.DM_DELAY_MIN, settings.DM_DELAY_MAX)
                logger.debug(f"Waiting {delay:.1f}s before next DM")
                await asyncio.sleep(delay)

        self.save_sessions()

        return {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "paused": False,
            "reason": "Batch complete",
        }


dm_sender_service = DMSenderService()
