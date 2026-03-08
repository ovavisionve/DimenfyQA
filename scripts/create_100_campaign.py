"""Create a new campaign targeting 100 leads for large-scale testing."""

import asyncio
import uuid

from sqlalchemy import select

from app.database import async_session
from app.models.client import Client
from app.models.campaign import Campaign


async def create():
    async with async_session() as db:
        # Get existing client or create one
        result = await db.execute(select(Client).where(Client.is_active.is_(True)).limit(1))
        client = result.scalar_one_or_none()

        if not client:
            client = Client(
                id=uuid.uuid4(),
                name="100 Leads Agency",
                business_type="agency",
                ig_accounts=["@automationagency"],
                settings={
                    "service_description": "We help businesses automate their lead generation using AI-powered Instagram DMs and automation tools.",
                },
            )
            db.add(client)
            await db.flush()
            print(f"Created client: {client.name} (ID: {client.id})")
        else:
            print(f"Using existing client: {client.name} (ID: {client.id})")

        # Create campaign with 100 leads target
        campaign = Campaign(
            id=uuid.uuid4(),
            client_id=client.id,
            name="100 Leads - Followers of @garyvee",
            source_type="followers",
            source_value="garyvee",
            status="pending",
            settings={"max_leads": 100},
        )
        db.add(campaign)
        await db.commit()

        print(f"\nCampaign created!")
        print(f"  Name: {campaign.name}")
        print(f"  ID: {campaign.id}")
        print(f"  Source: followers of @garyvee")
        print(f"  Max leads: 100")
        print(f"  Status: pending")
        print(f"\nGo to http://localhost:1000 and select this campaign to start it.")


if __name__ == "__main__":
    asyncio.run(create())
