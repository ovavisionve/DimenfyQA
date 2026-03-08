"""Clean all data and seed fresh test data for a pipeline run."""

import asyncio
import sys
import uuid
from pathlib import Path

# Ensure app module is importable when running from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.database import async_session
from app.models.client import Client
from app.models.campaign import Campaign


async def clean_and_seed():
    async with async_session() as db:
        # Delete everything in order (respecting FK constraints)
        await db.execute(text("DELETE FROM messages"))
        await db.execute(text("DELETE FROM leads"))
        await db.execute(text("DELETE FROM scrape_jobs"))
        await db.execute(text("DELETE FROM campaigns"))
        await db.execute(text("DELETE FROM clients"))
        await db.commit()
        print("Cleaned all tables.")

        # Create a test client
        client = Client(
            id=uuid.uuid4(),
            name="Test Agency",
            business_type="agency",
            ig_accounts=["@testagency"],
            settings={
                "service_description": "We help businesses automate their lead generation using AI-powered Instagram DMs.",
            },
        )
        db.add(client)
        await db.flush()

        # Create a profiles campaign with the target usernames
        campaign = Campaign(
            id=uuid.uuid4(),
            client_id=client.id,
            name="Pipeline Test - Profile Scraping",
            source_type="profiles",
            source_value="garyvee,tailopez,gaborekbuys,entrecoaching,digitalmarketer,marieforleo,amandafrancesofficial,jasonfladlien,russellbrunson,tikibarber",
            status="pending",
        )
        db.add(campaign)
        await db.commit()

        print(f"Created client: {client.id}")
        print(f"  Name: {client.name}")
        print(f"Created campaign: {campaign.id}")
        print(f"  Name: {campaign.name}")
        print(f"  Source: {campaign.source_type} -> {campaign.source_value}")
        print()
        print("To start the pipeline, POST to:")
        print(f"  http://localhost:1000/api/v1/campaigns/{campaign.id}/start")


if __name__ == "__main__":
    asyncio.run(clean_and_seed())
