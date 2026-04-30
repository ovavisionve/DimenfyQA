"""Dry-run test for the per-client DM prompt fix.

Picks an existing client by name (default: LegistAI), grabs up to N existing
leads from that client's database (no Apify call needed), runs the copywriting
service against them, and prints the generated DMs to stdout.

Nothing is written back to the DB — this is purely an output check so you can
verify the right brief is being applied before launching a paid campaign.

Usage (inside the running api/worker container):
    docker compose exec worker python scripts/test_dm_prompt.py
    docker compose exec worker python scripts/test_dm_prompt.py --client "Legist"
    docker compose exec worker python scripts/test_dm_prompt.py --limit 1
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import async_session
from app.models.client import Client
from app.models.lead import Lead
from app.services.copywriting_service import CopywritingService


async def main(client_name: str, limit: int) -> int:
    async with async_session() as db:
        client_result = await db.execute(
            select(Client).where(Client.name.ilike(f"%{client_name}%"))
        )
        clients = client_result.scalars().all()
        if not clients:
            print(f"[ERROR] No client found matching name ilike '%{client_name}%'")
            return 1
        if len(clients) > 1:
            print(f"[WARN] Multiple clients match '{client_name}':")
            for c in clients:
                print(f"  - {c.id}  {c.name}")
            print("Using the first one.")
        client = clients[0]

        settings = client.settings or {}
        dm_prompt = settings.get("dm_prompt", "") or ""
        scoring_prompt = settings.get("scoring_prompt", "") or ""

        print("=" * 80)
        print(f"Client: {client.name}  ({client.id})")
        print(f"  business_type        : {client.business_type}")
        print(f"  service_description  : {settings.get('service_description', '<not set>')[:80]}")
        print(f"  dm_prompt            : {len(dm_prompt)} chars")
        print(f"  scoring_prompt       : {len(scoring_prompt)} chars")
        if dm_prompt:
            print(f"  dm_prompt preview    : {dm_prompt[:120]}...")
        print("=" * 80)

        if not dm_prompt:
            print("[ERROR] This client has no dm_prompt saved — fix nothing to test.")
            return 1

        leads_result = await db.execute(
            select(Lead)
            .where(Lead.client_id == client.id)
            .where(Lead.ig_bio.isnot(None))
            .limit(limit)
        )
        leads = leads_result.scalars().all()
        if not leads:
            print(f"[ERROR] No leads found for client {client.name}.")
            return 1

        leads_data = []
        for lead in leads:
            leads_data.append({
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name or "",
                "ig_bio": lead.ig_bio or "",
                "ig_bio_clean": lead.ig_bio_clean or lead.ig_bio or "",
                "ig_website": lead.ig_website or "",
                "lead_category": lead.lead_category or "",
                "research_data": lead.research_data or "No research available",
            })

        client_config = {
            "business_type": client.business_type,
            "service_description": settings.get(
                "service_description",
                "B2B lead generation and automation services",
            ),
            "dm_prompt": dm_prompt,
            "content_analysis": None,
        }

        print(f"Generating DMs for {len(leads_data)} lead(s) — single Claude API call...")
        print("=" * 80)

        service = CopywritingService()
        results = service.generate_dms_batch(leads_data, client_config)

        for r in results:
            username = r.get("username", "?")
            dm_a = r.get("dm_a")
            dm_b = r.get("dm_b")
            print(f"\n--- @{username} ---")
            print(f"DM A: {dm_a}")
            print(f"DM B: {dm_b}")

        print("\n" + "=" * 80)
        print("CHECKLIST:")
        print("  [ ] Does the DM mention the client's actual product (not 'lead automation')?")
        print("  [ ] Is the tone correct (English/Spanish per the brief)?")
        print("  [ ] Does it follow the structure described in the brief?")
        print("  [ ] If the lead is off-target, is dm_a/dm_b null instead of forced?")
        print("=" * 80)
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="LegistAI", help="Client name (ilike match)")
    parser.add_argument("--limit", type=int, default=2, help="Max leads to test (default 2)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.client, args.limit)))
