import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead

logger = logging.getLogger(__name__)


async def check_duplicate(
    client_id: str, ig_username: str, db: AsyncSession
) -> bool:
    """Check if a lead already exists for this client."""
    result = await db.execute(
        select(Lead.id).where(
            Lead.client_id == client_id,
            Lead.ig_username == ig_username,
        )
    )
    return result.scalar_one_or_none() is not None


async def mark_duplicates(
    campaign_id: str, client_id: str, db: AsyncSession
) -> int:
    """Mark leads in a campaign that already exist for this client in other campaigns."""
    result = await db.execute(
        select(Lead).where(
            Lead.campaign_id == campaign_id,
            Lead.is_duplicate == False,  # noqa: E712
        )
    )
    leads = result.scalars().all()

    duplicates_found = 0
    for lead in leads:
        # Check if this username exists in another campaign for this client
        existing = await db.execute(
            select(Lead.id).where(
                Lead.client_id == client_id,
                Lead.ig_username == lead.ig_username,
                Lead.campaign_id != campaign_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            lead.is_duplicate = True
            duplicates_found += 1

    if duplicates_found:
        await db.flush()
        logger.info(
            f"Marked {duplicates_found} duplicates in campaign {campaign_id}"
        )
    return duplicates_found
