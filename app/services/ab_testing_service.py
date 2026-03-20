import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.schemas.ab_testing import ABTestResults, VariantStats

logger = logging.getLogger(__name__)


class ABTestingService:
    """Aggregates A/B test metrics for campaign DM variants."""

    @staticmethod
    def calculate_confidence(n_a: int, n_b: int, rate_a: float, rate_b: float) -> str:
        """Simple confidence calculation based on sample sizes.

        - low: either variant has < 30 sends
        - medium: both variants have 30-100 sends
        - high: both variants have > 100 sends
        """
        min_n = min(n_a, n_b)
        if min_n < 30:
            return "low"
        elif min_n <= 100:
            return "medium"
        else:
            return "high"

    async def get_campaign_ab_results(
        self, campaign_id: str, session: AsyncSession
    ) -> ABTestResults:
        """Return aggregated A/B test metrics for a campaign."""

        # Count sent per variant
        sent_a = await self._count(session, campaign_id, variant="A", statuses=["sent", "delivered"])
        sent_b = await self._count(session, campaign_id, variant="B", statuses=["sent", "delivered"])

        # Count replies per variant (gracefully handle missing columns)
        replied_a = await self._count_replied(session, campaign_id, variant="A")
        replied_b = await self._count_replied(session, campaign_id, variant="B")

        # Count positive replies per variant
        positive_a = await self._count_positive(session, campaign_id, variant="A")
        positive_b = await self._count_positive(session, campaign_id, variant="B")

        reply_rate_a = (replied_a / sent_a) if sent_a > 0 else 0.0
        reply_rate_b = (replied_b / sent_b) if sent_b > 0 else 0.0
        conversion_a = (positive_a / sent_a) if sent_a > 0 else 0.0
        conversion_b = (positive_b / sent_b) if sent_b > 0 else 0.0

        variant_a = VariantStats(
            sent=sent_a,
            replied=replied_a,
            reply_rate=round(reply_rate_a, 3),
            positive_replies=positive_a,
            conversion_rate=round(conversion_a, 3),
        )
        variant_b = VariantStats(
            sent=sent_b,
            replied=replied_b,
            reply_rate=round(reply_rate_b, 3),
            positive_replies=positive_b,
            conversion_rate=round(conversion_b, 3),
        )

        total_sent = sent_a + sent_b
        confidence = self.calculate_confidence(sent_a, sent_b, reply_rate_a, reply_rate_b)
        winner = self._determine_winner(variant_a, variant_b, total_sent)
        recommendation = self._build_recommendation(variant_a, variant_b, winner, confidence)

        return ABTestResults(
            campaign_id=campaign_id,
            variant_a=variant_a,
            variant_b=variant_b,
            winner=winner,
            confidence=confidence,
            total_sent=total_sent,
            recommendation=recommendation,
        )

    async def get_winner(
        self, campaign_id: str, session: AsyncSession
    ) -> Optional[str]:
        """Return the winning variant letter or None if insufficient data."""
        results = await self.get_campaign_ab_results(campaign_id, session)
        if results.total_sent < 10:
            return None
        return results.winner

    # ---- private helpers ----

    async def _count(
        self,
        session: AsyncSession,
        campaign_id: str,
        variant: str,
        statuses: list[str],
    ) -> int:
        result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.campaign_id == campaign_id,
                Lead.dm_variant_used == variant,
                Lead.status.in_(statuses),
            )
        )
        return result.scalar() or 0

    async def _count_replied(
        self, session: AsyncSession, campaign_id: str, variant: str
    ) -> int:
        """Count leads that have a reply. Handles missing replied_at column gracefully."""
        try:
            result = await session.execute(
                select(func.count(Lead.id)).where(
                    Lead.campaign_id == campaign_id,
                    Lead.dm_variant_used == variant,
                    Lead.replied_at.isnot(None),
                )
            )
            return result.scalar() or 0
        except Exception:
            logger.debug("replied_at column not available yet, returning 0 replies")
            return 0

    async def _count_positive(
        self, session: AsyncSession, campaign_id: str, variant: str
    ) -> int:
        """Count leads with a positive reply classification."""
        try:
            result = await session.execute(
                select(func.count(Lead.id)).where(
                    Lead.campaign_id == campaign_id,
                    Lead.dm_variant_used == variant,
                    Lead.reply_classification == "positive",
                )
            )
            return result.scalar() or 0
        except Exception:
            logger.debug("reply_classification column not available yet, returning 0 positive replies")
            return 0

    @staticmethod
    def _determine_winner(a: VariantStats, b: VariantStats, total_sent: int) -> Optional[str]:
        """Determine the winning variant based on reply rate, falling back to conversion rate."""
        if total_sent < 10:
            return None

        # Primary metric: reply rate
        if a.reply_rate > b.reply_rate:
            return "A"
        elif b.reply_rate > a.reply_rate:
            return "B"

        # Tiebreaker: conversion rate
        if a.conversion_rate > b.conversion_rate:
            return "A"
        elif b.conversion_rate > a.conversion_rate:
            return "B"

        return None  # Tied

    @staticmethod
    def _build_recommendation(
        a: VariantStats, b: VariantStats, winner: Optional[str], confidence: str
    ) -> str:
        if winner is None:
            if a.sent + b.sent < 10:
                return "Not enough data yet. Send more DMs to see results."
            return "Both variants are performing equally. Continue testing."

        if winner == "A" and b.reply_rate > 0:
            pct_diff = round(((a.reply_rate - b.reply_rate) / b.reply_rate) * 100)
            rec = f"Variant A has {pct_diff}% higher reply rate."
        elif winner == "B" and a.reply_rate > 0:
            pct_diff = round(((b.reply_rate - a.reply_rate) / a.reply_rate) * 100)
            rec = f"Variant B has {pct_diff}% higher reply rate."
        elif winner == "A":
            rec = "Variant A is performing better."
        else:
            rec = "Variant B is performing better."

        if confidence == "high":
            rec += f" High confidence — continue with {winner}."
        elif confidence == "medium":
            rec += f" Medium confidence — consider switching to {winner}."
        else:
            rec += " Low confidence — more data needed."

        return rec


ab_testing_service = ABTestingService()
