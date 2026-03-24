import logging
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.lead import Lead

logger = logging.getLogger(__name__)


class AnalyticsService:
    async def get_campaign_analytics(self, campaign_id: str, db: AsyncSession) -> dict:
        """Full analytics for a campaign."""

        # --- Funnel counts ---
        funnel_query = select(
            func.count().label("total"),
            func.count().filter(Lead.score.isnot(None)).label("scored"),
            func.count().filter(Lead.research_data.isnot(None)).label("researched"),
            func.count().filter(Lead.dm_message.isnot(None)).label("dm_ready"),
            func.count().filter(Lead.status == "sent").label("sent"),
            func.count().filter(Lead.replied_at.isnot(None)).label("replied"),
        ).where(Lead.campaign_id == campaign_id)

        result = await db.execute(funnel_query)
        row = result.one()
        total = row.total or 0
        scored = row.scored or 0
        researched = row.researched or 0
        dm_ready = row.dm_ready or 0
        sent = row.sent or 0
        replied = row.replied or 0

        funnel = [
            {"name": "scraped", "count": total, "percentage": 100.0 if total else 0.0},
            {"name": "scored", "count": scored, "percentage": round(scored / total * 100, 1) if total else 0.0},
            {"name": "researched", "count": researched, "percentage": round(researched / total * 100, 1) if total else 0.0},
            {"name": "dm_ready", "count": dm_ready, "percentage": round(dm_ready / total * 100, 1) if total else 0.0},
            {"name": "sent", "count": sent, "percentage": round(sent / total * 100, 1) if total else 0.0},
            {"name": "replied", "count": replied, "percentage": round(replied / total * 100, 1) if total else 0.0},
        ]

        # --- Response rate ---
        response_rate = round(replied / sent * 100, 1) if sent else 0.0

        # --- Average score ---
        avg_result = await db.execute(
            select(func.avg(Lead.score)).where(
                Lead.campaign_id == campaign_id, Lead.score.isnot(None)
            )
        )
        avg_score = avg_result.scalar()
        avg_score = round(float(avg_score), 1) if avg_score is not None else 0.0

        # --- Score distribution ---
        score_dist_query = select(
            func.count().filter(Lead.score.between(0, 20)).label("r_0_20"),
            func.count().filter(Lead.score.between(21, 40)).label("r_21_40"),
            func.count().filter(Lead.score.between(41, 60)).label("r_41_60"),
            func.count().filter(Lead.score.between(61, 80)).label("r_61_80"),
            func.count().filter(Lead.score.between(81, 100)).label("r_81_100"),
        ).where(Lead.campaign_id == campaign_id, Lead.score.isnot(None))

        dist_result = await db.execute(score_dist_query)
        dist_row = dist_result.one()

        score_distribution = [
            {"range_label": "0-20", "count": dist_row.r_0_20 or 0},
            {"range_label": "21-40", "count": dist_row.r_21_40 or 0},
            {"range_label": "41-60", "count": dist_row.r_41_60 or 0},
            {"range_label": "61-80", "count": dist_row.r_61_80 or 0},
            {"range_label": "81-100", "count": dist_row.r_81_100 or 0},
        ]

        # --- Category breakdown ---
        cat_query = select(
            Lead.lead_category,
            func.count().label("count"),
        ).where(
            Lead.campaign_id == campaign_id,
            Lead.lead_category.isnot(None),
        ).group_by(Lead.lead_category).order_by(func.count().desc())

        cat_result = await db.execute(cat_query)
        cat_rows = cat_result.all()
        total_categorized = sum(r.count for r in cat_rows) if cat_rows else 0

        category_breakdown = [
            {
                "category": r.lead_category,
                "count": r.count,
                "percentage": round(r.count / total_categorized * 100, 1) if total_categorized else 0.0,
            }
            for r in cat_rows
        ]

        # --- Timeline (daily sent/replied aggregation) ---
        timeline_query = select(
            func.date(Lead.sent_at).label("date"),
            func.count().label("sent_count"),
            func.count().filter(Lead.replied_at.isnot(None)).label("replied_count"),
        ).where(
            Lead.campaign_id == campaign_id,
            Lead.sent_at.isnot(None),
        ).group_by(func.date(Lead.sent_at)).order_by(func.date(Lead.sent_at))

        timeline_result = await db.execute(timeline_query)
        timeline_rows = timeline_result.all()

        timeline = [
            {
                "date": str(r.date),
                "sent_count": r.sent_count or 0,
                "replied_count": r.replied_count or 0,
            }
            for r in timeline_rows
        ]

        # --- Conversion funnel (percentage at each stage relative to previous) ---
        stages = [total, scored, researched, dm_ready, sent, replied]
        stage_names = ["scraped", "scored", "researched", "dm_ready", "sent", "replied"]
        conversion_funnel = []
        for i, (name, count) in enumerate(zip(stage_names, stages)):
            prev = stages[i - 1] if i > 0 else count
            pct = round(count / prev * 100, 1) if prev else 0.0
            conversion_funnel.append({"stage": name, "count": count, "conversion_pct": pct})

        return {
            "campaign_id": campaign_id,
            "funnel": funnel,
            "response_rate": response_rate,
            "score_distribution": score_distribution,
            "category_breakdown": category_breakdown,
            "timeline": timeline,
            "avg_score": avg_score,
            "conversion_funnel": conversion_funnel,
            "total_leads": total,
            "total_sent": sent,
            "total_replied": replied,
        }

    async def get_client_analytics(self, client_id: str, db: AsyncSession) -> dict:
        """Aggregate analytics across all campaigns for a client."""

        # Total campaigns
        camp_result = await db.execute(
            select(func.count()).select_from(Campaign).where(Campaign.client_id == client_id)
        )
        total_campaigns = camp_result.scalar() or 0

        # Aggregate lead stats
        agg_query = select(
            func.count().label("total_leads"),
            func.avg(Lead.score).label("avg_score"),
            func.count().filter(Lead.status == "sent").label("total_sent"),
            func.count().filter(Lead.replied_at.isnot(None)).label("total_replied"),
            func.count().filter(Lead.dm_message.isnot(None)).label("total_dm_ready"),
            func.count().filter(Lead.score.isnot(None)).label("total_scored"),
        ).where(Lead.client_id == client_id)

        result = await db.execute(agg_query)
        row = result.one()

        total_leads = row.total_leads or 0
        total_sent = row.total_sent or 0
        total_replied = row.total_replied or 0
        avg_score = round(float(row.avg_score), 1) if row.avg_score is not None else 0.0
        response_rate = round(total_replied / total_sent * 100, 1) if total_sent else 0.0

        # Category breakdown across all campaigns
        cat_query = select(
            Lead.lead_category,
            func.count().label("count"),
        ).where(
            Lead.client_id == client_id,
            Lead.lead_category.isnot(None),
        ).group_by(Lead.lead_category).order_by(func.count().desc())

        cat_result = await db.execute(cat_query)
        cat_rows = cat_result.all()
        total_categorized = sum(r.count for r in cat_rows) if cat_rows else 0

        category_breakdown = [
            {
                "category": r.lead_category,
                "count": r.count,
                "percentage": round(r.count / total_categorized * 100, 1) if total_categorized else 0.0,
            }
            for r in cat_rows
        ]

        return {
            "client_id": client_id,
            "total_campaigns": total_campaigns,
            "total_leads": total_leads,
            "total_sent": total_sent,
            "total_replied": total_replied,
            "avg_score": avg_score,
            "response_rate": response_rate,
            "total_scored": row.total_scored or 0,
            "total_dm_ready": row.total_dm_ready or 0,
            "category_breakdown": category_breakdown,
        }

    async def get_top_performing_campaigns(
        self, client_id: str, db: AsyncSession, limit: int = 10
    ) -> list:
        """Campaigns ranked by response rate."""

        # Subquery for per-campaign stats
        sent_count = func.count().filter(Lead.status == "sent").label("sent_count")
        replied_count = func.count().filter(Lead.replied_at.isnot(None)).label("replied_count")

        query = (
            select(
                Campaign.id,
                Campaign.name,
                Campaign.status,
                func.count().label("total_leads"),
                sent_count,
                replied_count,
                func.avg(Lead.score).label("avg_score"),
            )
            .join(Lead, Lead.campaign_id == Campaign.id)
            .where(Campaign.client_id == client_id)
            .group_by(Campaign.id, Campaign.name, Campaign.status)
            .order_by(
                case(
                    (sent_count == 0, 0),
                    else_=replied_count * 100 / sent_count,
                ).desc()
            )
            .limit(limit)
        )

        result = await db.execute(query)
        rows = result.all()

        return [
            {
                "campaign_id": str(r.id),
                "name": r.name,
                "status": r.status,
                "total_leads": r.total_leads,
                "sent": r.sent_count,
                "replied": r.replied_count,
                "response_rate": round(r.replied_count / r.sent_count * 100, 1) if r.sent_count else 0.0,
                "avg_score": round(float(r.avg_score), 1) if r.avg_score is not None else 0.0,
            }
            for r in rows
        ]


analytics_service = AnalyticsService()
