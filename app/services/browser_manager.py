"""
BrowserManager — Multi-account Playwright orchestrator.

Drop-in replacement for DMSenderService when USE_PLAYWRIGHT=True.
Manages a pool of IGBrowserAccount instances with round-robin rotation,
rate limiting, warm-up, cooldowns, and all the same security guarantees
as the instagrapi-based DMSenderService.

Usage in sending_tasks.py is transparent — the task imports
get_sender_service() which returns either DMSenderService or
BrowserManager based on the USE_PLAYWRIGHT config flag.
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.services.browser_automation_service import IGBrowserAccount
from app.services.webhook_service import webhook_service

logger = logging.getLogger(__name__)

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


class BrowserManager:
    """
    Multi-account Playwright orchestrator for Instagram DMs.

    Same public interface as DMSenderService so the Celery tasks
    don't need to know which engine is running underneath.
    """

    def __init__(self):
        self._session_path = Path(settings.PW_BROWSER_DATA_DIR)
        self._session_path.mkdir(parents=True, exist_ok=True)
        self._accounts: list[IGBrowserAccount] = []
        self._current_account_idx = 0

    def _init_accounts(self):
        if self._accounts:
            return

        multi = _parse_accounts(settings.IG_ACCOUNTS)
        if multi:
            for acc in multi:
                self._accounts.append(IGBrowserAccount(
                    username=acc["username"],
                    password=acc["password"],
                    proxy=acc["proxy"],
                    session_dir=self._session_path,
                ))
            logger.info(f"[Playwright] Configured {len(self._accounts)} accounts for rotation")
        elif settings.IG_USERNAME and settings.IG_PASSWORD:
            self._accounts.append(IGBrowserAccount(
                username=settings.IG_USERNAME,
                password=settings.IG_PASSWORD,
                proxy=settings.PROXY_URL,
                session_dir=self._session_path,
            ))
            logger.info("[Playwright] Configured 1 account (single mode)")

    # -- Login --

    async def login(self) -> bool:
        """Login all configured accounts. Returns True if at least one succeeds."""
        self._init_accounts()

        if not self._accounts:
            logger.error("No IG accounts configured (set IG_USERNAME/IG_PASSWORD or IG_ACCOUNTS)")
            return False

        for acc in self._accounts:
            if acc.proxy and not acc.validate_proxy():
                logger.warning(f"Proxy failed for @{acc.username}, proceeding without proxy")

        success_count = 0
        for acc in self._accounts:
            in_cooldown, reason = acc.is_in_cooldown()
            if acc.is_blocked and in_cooldown:
                logger.warning(f"Skipping @{acc.username}: {reason}")
                continue
            if await acc.login():
                success_count += 1

        if success_count == 0:
            logger.error("[Playwright] All account logins failed")
            return False

        logger.info(f"[Playwright] Logged in to {success_count}/{len(self._accounts)} accounts")
        return True

    # -- Account rotation --

    def _get_next_account(self) -> IGBrowserAccount | None:
        if not self._accounts:
            return None
        for _ in range(len(self._accounts)):
            acc = self._accounts[self._current_account_idx]
            self._current_account_idx = (self._current_account_idx + 1) % len(self._accounts)
            if acc._logged_in and not acc.is_blocked:
                in_cooldown, _ = acc.is_in_cooldown()
                if not in_cooldown:
                    return acc
        return None

    # -- DM sending --

    async def send_dm(self, username: str, message: str) -> dict:
        account = self._get_next_account()
        if not account:
            return {"success": False, "error": "No available IG accounts (all blocked/cooldown)"}
        return await account.send_dm(username, message)

    async def pre_send_check(self, username: str) -> bool:
        if not settings.PRE_SEND_CHECK_PUBLIC:
            return True
        account = self._get_next_account()
        if not account:
            return True
        return await account.check_user_public(username)

    async def save_sessions(self):
        for acc in self._accounts:
            await acc.save_session()

    def get_accounts_health(self) -> list[dict]:
        self._init_accounts()
        return [acc.get_health() for acc in self._accounts]

    # -- DB queries (identical to DMSenderService) --

    async def get_daily_send_count(self, db: AsyncSession) -> int:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.status == "sent",
                Lead.sent_at >= today_start,
            )
        )
        return result.scalar() or 0

    def _get_effective_daily_limit(self) -> int:
        if not self._accounts:
            return settings.DAILY_DM_LIMIT
        total = sum(
            acc.get_warmup_limit()
            for acc in self._accounts
            if acc._logged_in and not acc.is_blocked
        )
        return total if total > 0 else settings.DAILY_DM_LIMIT

    async def get_next_leads_to_send(
        self, campaign_id: str, db: AsyncSession, limit: int = 10
    ) -> list[Lead]:
        result = await db.execute(
            select(Lead).where(
                Lead.campaign_id == campaign_id,
                Lead.status.in_(["dm_ready", "retry"]),
                Lead.send_attempts < MAX_SEND_ATTEMPTS,
                Lead.ig_is_private.is_not(True),
            ).order_by(Lead.score.desc()).limit(limit)
        )
        return list(result.scalars().all())

    def _get_remaining_window_seconds(self, start: str, end: str, tz_name: str) -> float:
        """Calculate remaining seconds in the sending window for even DM distribution."""
        if not start or not end or not tz_name:
            now_utc = datetime.now(timezone.utc)
            seconds_left = (now_utc.replace(hour=23, minute=59, second=59) - now_utc).total_seconds()
            return max(seconds_left, 3600)
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name)
            now_local = datetime.now(tz)
            start_h, start_m = map(int, start.split(":"))
            end_h, end_m = map(int, end.split(":"))
            end_time = now_local.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m
            if end_minutes <= start_minutes:
                current_minutes = now_local.hour * 60 + now_local.minute
                if current_minutes >= start_minutes or current_minutes < end_minutes:
                    if now_local.hour >= start_h:
                        end_time += timedelta(days=1)
                else:
                    end_time += timedelta(days=1)
            remaining = (end_time - now_local).total_seconds()
            return max(remaining, 3600)
        except Exception:
            return 24 * 3600

    # -- Main campaign sending pipeline --

    async def send_campaign_dms(
        self,
        campaign_id: str,
        db: AsyncSession,
        progress_callback=None,
    ) -> dict:
        """
        Send DMs for a campaign using Playwright browsers.
        Same interface and return format as DMSenderService.send_campaign_dms().
        """
        from app.models.campaign import Campaign
        campaign_result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign_obj = campaign_result.scalar_one_or_none()
        campaign_settings = (campaign_obj.settings or {}) if campaign_obj else {}
        sending_start = campaign_settings.get("sending_hours_start", "")
        sending_end = campaign_settings.get("sending_hours_end", "")
        sending_tz = campaign_settings.get("sending_timezone", "")

        daily_count = await self.get_daily_send_count(db)
        daily_limit = self._get_effective_daily_limit()

        if daily_count >= daily_limit:
            logger.warning(f"Daily DM limit reached ({daily_count}/{daily_limit})")
            return {
                "sent_count": 0, "failed_count": 0, "skipped_count": 0,
                "paused": True,
                "reason": f"Daily limit reached ({daily_count}/{daily_limit})",
            }

        remaining_today = daily_limit - daily_count
        leads = await self.get_next_leads_to_send(campaign_id, db, limit=remaining_today)

        if not leads:
            return {
                "sent_count": 0, "failed_count": 0, "skipped_count": 0,
                "paused": False, "reason": "No leads to send",
            }

        window_seconds = self._get_remaining_window_seconds(sending_start, sending_end, sending_tz)
        even_delay = window_seconds / len(leads) if len(leads) > 1 else 0
        logger.info(
            f"[Playwright] Sending DMs to {len(leads)} leads (daily: {daily_count}/{daily_limit}), "
            f"window={window_seconds/3600:.1f}h, interval={even_delay/60:.1f}min"
        )

        sent_count = 0
        failed_count = 0
        skipped_count = 0

        for i, lead in enumerate(leads):
            # Pre-send public check
            if settings.PRE_SEND_CHECK_PUBLIC:
                is_public = await self.pre_send_check(lead.ig_username)
                if not is_public:
                    lead.status = "failed"
                    lead.send_error = "Target account is private"
                    lead.delivery_status = "skipped_private"
                    lead.ig_is_private = True
                    await db.commit()
                    skipped_count += 1
                    logger.info(f"Skipped @{lead.ig_username}: private account")
                    continue

            # A/B test variant selection (same logic as DMSenderService)
            if lead.dm_variant_used in ("A", "B") and lead.send_attempts > 0:
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

            # Send via Playwright (async — unlike instagrapi which is sync)
            result = await self.send_dm(lead.ig_username, message)

            if result["success"]:
                lead.status = "sent"
                lead.sent_at = datetime.now(timezone.utc)
                lead.delivery_status = "sent"
                lead.send_error = None
                sent_count += 1
                logger.info(f"[PW] Sent DM ({variant}) to @{lead.ig_username} [{sent_count}/{len(leads)}]")

                try:
                    await webhook_service.trigger_event(
                        client_id=str(lead.client_id),
                        event_type="dm.sent",
                        payload={
                            "lead_id": str(lead.id),
                            "ig_username": lead.ig_username,
                            "campaign_id": str(lead.campaign_id),
                            "variant": variant,
                            "engine": "playwright",
                        },
                        db=db,
                    )
                except Exception:
                    pass
            else:
                lead.send_attempts += 1
                lead.send_error = result.get("error", "Unknown error")

                if result.get("is_rate_limited") or result.get("is_cooldown"):
                    lead.status = "retry"
                    lead.delivery_status = "rate_limited"
                    await db.commit()
                    return {
                        "sent_count": sent_count, "failed_count": failed_count,
                        "skipped_count": skipped_count,
                        "paused": True, "reason": result.get("error", "Rate limited"),
                    }

                if result.get("is_not_found"):
                    lead.status = "failed"
                    lead.delivery_status = "user_not_found"
                    failed_count += 1
                    await db.commit()
                    continue

                if result.get("is_challenge") or result.get("is_block"):
                    lead.status = "retry"
                    lead.delivery_status = "challenge" if result.get("is_challenge") else "blocked"
                    await db.commit()

                    usable = self._get_next_account()
                    if usable is None:
                        reason = "All accounts challenged/blocked — waiting for cooldown"
                        logger.warning(f"Pausing campaign: {reason}")
                        return {
                            "sent_count": sent_count, "failed_count": failed_count,
                            "skipped_count": skipped_count,
                            "paused": True, "reason": reason,
                        }
                    else:
                        logger.warning(f"Account hit challenge, rotating to @{usable.username}")
                        continue

                if lead.send_attempts >= MAX_SEND_ATTEMPTS:
                    lead.status = "failed"
                    lead.delivery_status = "max_attempts"
                    failed_count += 1
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
                    progress_callback(i + 1, len(leads), lead.ig_username, result["success"])
                except Exception:
                    pass

            # Distribute DMs evenly across sending window
            if i < len(leads) - 1:
                base_min = settings.DM_DELAY_MIN
                base_max = settings.DM_DELAY_MAX
                if not result["success"]:
                    base_min = int(base_min * 1.5)
                    base_max = int(base_max * 2)
                safety_delay = random.uniform(base_min, base_max)
                safety_delay += random.uniform(-5, 10)
                safety_delay = max(15, safety_delay)

                delay = max(safety_delay, even_delay)
                if even_delay > safety_delay:
                    jitter = delay * 0.1
                    delay += random.uniform(-jitter, jitter)

                logger.info(f"Next DM in {delay/60:.1f}min (even={even_delay/60:.1f}min, safety={safety_delay:.0f}s)")
                await asyncio.sleep(delay)

        await self.save_sessions()

        return {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "paused": False,
            "reason": "Batch complete",
        }

    # -- Cleanup --

    async def close_all(self):
        """Close all browser instances."""
        for acc in self._accounts:
            await acc.close()
        logger.info("[Playwright] All browsers closed")


# ---------------------------------------------------------------------------
# Factory: pick the right sender based on config
# ---------------------------------------------------------------------------

def get_sender_service():
    """
    Returns either BrowserManager (Playwright) or DMSenderService (instagrapi)
    based on the USE_PLAYWRIGHT config flag.

    Usage:
        sender = get_sender_service()
        await sender.login()
        result = await sender.send_campaign_dms(campaign_id, db)
    """
    if settings.USE_PLAYWRIGHT:
        logger.info("Using Playwright + Stealth engine for DM sending")
        return BrowserManager()
    else:
        from app.services.dm_sender_service import DMSenderService
        logger.info("Using instagrapi engine for DM sending")
        return DMSenderService()
