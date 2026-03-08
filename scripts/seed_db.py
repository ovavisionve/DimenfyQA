"""Seed database with test data for development."""

import asyncio
import sys
import uuid
from pathlib import Path

# Ensure app module is importable when running from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import async_session
from app.models.client import Client
from app.models.campaign import Campaign
from app.models.lead import Lead


async def seed():
    async with async_session() as db:
        # Check if already seeded
        result = await db.execute(select(Client).limit(1))
        if result.scalar_one_or_none():
            print("Database already has data, skipping seed.")
            return

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

        # Create a test campaign
        campaign = Campaign(
            id=uuid.uuid4(),
            client_id=client.id,
            name="Test Campaign - Followers of @marketingguru",
            source_type="followers",
            source_value="marketingguru",
            status="pending",
        )
        db.add(campaign)
        await db.flush()

        # Create sample leads
        sample_leads = [
            {
                "ig_username": "businesscoach_maria",
                "ig_full_name": "Maria Lopez - Business Coach",
                "ig_bio": "Helping entrepreneurs scale to 6 figures | Speaker | Author of 'Scale Smart'",
                "ig_website": "https://marialopez.com",
                "ig_category": "Coach",
                "ig_follower_count": 25000,
                "ig_following_count": 1200,
                "ig_is_private": False,
                "score": 85,
                "lead_category": "coach",
                "status": "scored",
            },
            {
                "ig_username": "ecomstore_daily",
                "ig_full_name": "Daily Ecom Store",
                "ig_bio": "Premium lifestyle products | Free shipping worldwide | Shop now",
                "ig_website": "https://dailyecom.com",
                "ig_category": "Shopping & Retail",
                "ig_follower_count": 50000,
                "ig_following_count": 500,
                "ig_is_private": False,
                "score": 72,
                "lead_category": "ecommerce",
                "status": "scored",
            },
            {
                "ig_username": "random_personal_user",
                "ig_full_name": "Just a person",
                "ig_bio": "Living my best life",
                "ig_website": None,
                "ig_category": None,
                "ig_follower_count": 150,
                "ig_following_count": 300,
                "ig_is_private": True,
                "score": 5,
                "lead_category": "other",
                "status": "scored",
            },
        ]

        for lead_data in sample_leads:
            lead = Lead(
                campaign_id=campaign.id,
                client_id=client.id,
                **lead_data,
            )
            db.add(lead)

        await db.commit()
        print(f"Seeded: 1 client, 1 campaign, {len(sample_leads)} leads")
        print(f"Client ID: {client.id}")
        print(f"Campaign ID: {campaign.id}")


if __name__ == "__main__":
    asyncio.run(seed())
