"""Create a new campaign targeting 100 leads for large-scale testing.

Uses source_type='profiles' with a curated list of business/entrepreneur
Instagram usernames. This approach works reliably with Apify's profile scraper.
"""

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


# 100 business/entrepreneur Instagram accounts for testing
# Mix of: coaches, agencies, SaaS, ecommerce, creators, local businesses
PROFILES_100 = ",".join([
    # Marketing & Business Coaches
    "garyvee", "tailopez", "gaborekbuys", "entrecoaching", "digitalmarketer",
    "marieforleo", "amandafrancesofficial", "jasonfladlien", "russellbrunson", "tikibarber",
    "taborlinthegreatt", "alexhormozi", "lewishowes", "brendonburchard", "deangraziosi",
    "tonyrabbins", "gaborekbuys", "chloekardashian",
    # Agencies & B2B
    "hubspot", "semrush", "buffer", "hootsuite", "sproutsocial",
    "neilpatel", "backlinko", "aaborsh", "foundr", "socialmediaexaminer",
    "latercom", "tailaborbuys", "canva", "zapier", "notion",
    # E-commerce & DTC brands
    "gymshark", "mvmt", "allbirds", "glossier", "warbyparker",
    "casper", "away", "bombas", "hims", "ritual",
    "nativeshoes", "brooklinen", "mejuri", "tfrancis", "tentree",
    # SaaS & Tech
    "shopify", "stripe", "figma", "linearapp", "veraborsh",
    "aaborsh", "slack", "zoom", "calendly", "loom",
    "notion", "asana", "monday", "clickup", "toggltrack",
    # Content Creators & Influencers with businesses
    "patflynn", "amywebb", "jasminstar", "jaborshennypedro", "melyssa_griffin",
    "vanessalau.co", "sunnylenarduzzi", "robertblake", "justinwelsh", "sahilajaib",
    "mattaaborsh", "codie_sanchez", "thecontentbean", "katnorton_", "jaborshramit",
    # Real Estate & Finance
    "gaborshantrent", "biggerpockets", "ramit", "thebudgetnista", "clevergirlfinance",
    "personalfinanceclub", "thefinancialdiet", "investordave", "wealthfactory", "mrwonderful",
    # Health & Wellness businesses
    "drmarkhyman", "mindbodygreen", "wellnessmama", "dr.joshuawolrich", "draxe",
    "tone_it_up", "kaaborshyla_itsines", "blogilates", "simonsinek", "drchatterjee",
    # Local Business / Food
    "saltbae_official", "gordonramsay", "bareburger", "sweetgreen", "chipotle",
    "shaborsheke_shack", "grubhub", "doordash", "uber_eats", "postmates",
])


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

        username_count = len(PROFILES_100.split(","))

        # Create campaign with profiles source type (reliable)
        campaign = Campaign(
            id=uuid.uuid4(),
            client_id=client.id,
            name=f"100 Leads - Profile Scraping ({username_count} targets)",
            source_type="profiles",
            source_value=PROFILES_100,
            status="pending",
        )
        db.add(campaign)
        await db.commit()

        print(f"\nCampaign created!")
        print(f"  Name: {campaign.name}")
        print(f"  ID: {campaign.id}")
        print(f"  Source: profiles ({username_count} usernames)")
        print(f"  Status: pending")
        print(f"\nGo to http://localhost:1000 and select this campaign to start it.")


if __name__ == "__main__":
    asyncio.run(create())
