"""Tests for campaign sending schedule with timezone support."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


def is_within_sending_hours(
    sending_start: str,
    sending_end: str,
    sending_tz: str,
    now: datetime | None = None,
) -> bool:
    """Check if current time is within the campaign's sending hours.

    Replicates the logic from dm_sender_service.send_campaign_dms().
    """
    if not sending_start or not sending_end or not sending_tz:
        return True  # No schedule configured = always allowed

    tz = ZoneInfo(sending_tz)
    now_local = now.astimezone(tz) if now else datetime.now(tz)

    start_h, start_m = map(int, sending_start.split(":"))
    end_h, end_m = map(int, sending_end.split(":"))

    current_minutes = now_local.hour * 60 + now_local.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes < end_minutes
    else:
        # Overnight schedule (e.g., 22:00 - 06:00)
        return current_minutes >= start_minutes or current_minutes < end_minutes


class TestSendingSchedule:
    """Tests for sending schedule time checks."""

    def test_no_schedule_always_allowed(self):
        assert is_within_sending_hours("", "", "") is True

    def test_within_hours(self):
        # 10:30 is within 09:00-21:00
        now = datetime(2026, 3, 25, 10, 30, tzinfo=ZoneInfo("America/Caracas"))
        assert is_within_sending_hours("09:00", "21:00", "America/Caracas", now) is True

    def test_before_start(self):
        # 07:00 is before 09:00
        now = datetime(2026, 3, 25, 7, 0, tzinfo=ZoneInfo("America/Caracas"))
        assert is_within_sending_hours("09:00", "21:00", "America/Caracas", now) is False

    def test_after_end(self):
        # 22:00 is after 21:00
        now = datetime(2026, 3, 25, 22, 0, tzinfo=ZoneInfo("America/Caracas"))
        assert is_within_sending_hours("09:00", "21:00", "America/Caracas", now) is False

    def test_at_exact_start(self):
        # 09:00 is the start — should be allowed
        now = datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("America/Caracas"))
        assert is_within_sending_hours("09:00", "21:00", "America/Caracas", now) is True

    def test_at_exact_end(self):
        # 21:00 is the end — should NOT be allowed (exclusive)
        now = datetime(2026, 3, 25, 21, 0, tzinfo=ZoneInfo("America/Caracas"))
        assert is_within_sending_hours("09:00", "21:00", "America/Caracas", now) is False

    def test_overnight_schedule_within(self):
        # 23:00 is within 22:00-06:00
        now = datetime(2026, 3, 25, 23, 0, tzinfo=ZoneInfo("America/Caracas"))
        assert is_within_sending_hours("22:00", "06:00", "America/Caracas", now) is True

    def test_overnight_schedule_early_morning(self):
        # 03:00 is within 22:00-06:00
        now = datetime(2026, 3, 26, 3, 0, tzinfo=ZoneInfo("America/Caracas"))
        assert is_within_sending_hours("22:00", "06:00", "America/Caracas", now) is True

    def test_overnight_schedule_outside(self):
        # 12:00 is outside 22:00-06:00
        now = datetime(2026, 3, 25, 12, 0, tzinfo=ZoneInfo("America/Caracas"))
        assert is_within_sending_hours("22:00", "06:00", "America/Caracas", now) is False

    def test_different_timezone(self):
        # 10:00 UTC is 06:00 Caracas (VET -04:00) — before 09:00
        now = datetime(2026, 3, 25, 10, 0, tzinfo=ZoneInfo("UTC"))
        assert is_within_sending_hours("09:00", "21:00", "America/Caracas", now) is False

    def test_different_timezone_within(self):
        # 15:00 UTC is 11:00 Caracas — within 09:00-21:00
        now = datetime(2026, 3, 25, 15, 0, tzinfo=ZoneInfo("UTC"))
        assert is_within_sending_hours("09:00", "21:00", "America/Caracas", now) is True

    def test_half_hour_granularity(self):
        # 09:30 with start at 09:30
        now = datetime(2026, 3, 25, 9, 30, tzinfo=ZoneInfo("America/Bogota"))
        assert is_within_sending_hours("09:30", "18:00", "America/Bogota", now) is True

    def test_bogota_timezone(self):
        now = datetime(2026, 3, 25, 14, 0, tzinfo=ZoneInfo("America/Bogota"))
        assert is_within_sending_hours("08:00", "20:00", "America/Bogota", now) is True
