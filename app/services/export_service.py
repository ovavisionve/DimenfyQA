import csv
import io
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead

logger = logging.getLogger(__name__)

EXPORT_CSV_COLUMNS = [
    "ig_username",
    "ig_full_name",
    "ig_bio_clean",
    "ig_website",
    "ig_category",
    "ig_follower_count",
    "score",
    "lead_category",
    "dm_message",
]


class ExportService:
    async def export_csv(self, campaign_id: str, db: AsyncSession) -> str:
        """Export DM-ready leads as CSV string for JarveePro import."""
        leads = await self._get_dm_ready_leads(campaign_id, db)

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=EXPORT_CSV_COLUMNS)
        writer.writeheader()

        for lead in leads:
            writer.writerow({
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name or "",
                "ig_bio_clean": lead.ig_bio_clean or "",
                "ig_website": lead.ig_website or "",
                "ig_category": lead.ig_category or "",
                "ig_follower_count": lead.ig_follower_count or 0,
                "score": lead.score or 0,
                "lead_category": lead.lead_category or "",
                "dm_message": lead.dm_message or "",
            })

        return output.getvalue()

    async def export_json(self, campaign_id: str, db: AsyncSession) -> list[dict]:
        """Export DM-ready leads as JSON list."""
        leads = await self._get_dm_ready_leads(campaign_id, db)

        return [
            {
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name,
                "ig_bio_clean": lead.ig_bio_clean,
                "ig_website": lead.ig_website,
                "ig_category": lead.ig_category,
                "ig_follower_count": lead.ig_follower_count,
                "score": lead.score,
                "score_reason": lead.score_reason,
                "lead_category": lead.lead_category,
                "research_summary": lead.research_summary,
                "dm_message": lead.dm_message,
                "dm_variant_b": lead.dm_variant_b,
            }
            for lead in leads
        ]

    async def _get_dm_ready_leads(
        self, campaign_id: str, db: AsyncSession
    ) -> list[Lead]:
        result = await db.execute(
            select(Lead).where(
                Lead.campaign_id == campaign_id,
                Lead.status == "dm_ready",
                Lead.dm_message.isnot(None),
            ).order_by(Lead.score.desc())
        )
        return list(result.scalars().all())


export_service = ExportService()
