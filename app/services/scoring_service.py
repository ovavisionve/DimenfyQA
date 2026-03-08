import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.utils.text_cleanup import clean_bio

logger = logging.getLogger(__name__)

# Batch size: how many leads per single API call
BATCH_SIZE = 20
# Max parallel batch API calls
MAX_PARALLEL_BATCHES = 3

BATCH_SCORING_PROMPT = """Eres un asistente de calificación de leads para una agencia de automatización B2B.

Evalúa cada perfil de Instagram y asigna un score de 0 a 100.

## Criterios de scoring:
- Es un negocio o emprendedor (0-25 puntos)
- Tiene entre 200 y 1M followers (0-15 puntos)
- Su bio menciona servicios, productos o negocio (0-20 puntos)
- Podría beneficiarse de lead generation B2B (0-25 puntos)
- Tiene website (0-10 puntos)
- Perfil público (0-5 puntos, 0 si es privado)

## Leads a evaluar:
{leads_json}

## Output:
Responde SOLO un JSON array válido, sin markdown ni backticks. Cada elemento debe tener:
[
  {{
    "username": "<ig_username exacto>",
    "score": <número 0-100>,
    "reason": "<explicación de 1-2 oraciones>",
    "category": "<una de: coach, ecommerce, saas, agency, creator, local_business, other>",
    "bio_clean": "<bio limpia sin emojis ni line breaks>"
  }}
]

IMPORTANTE: Devuelve EXACTAMENTE un resultado por cada lead de la lista. El JSON array debe tener {lead_count} elementos."""


class ScoringService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def score_batch(self, leads_data: list[dict]) -> list[dict]:
        """Score a batch of leads in a single API call. Returns list of score dicts."""
        leads_for_prompt = []
        for ld in leads_data:
            leads_for_prompt.append({
                "username": ld.get("ig_username", ""),
                "name": ld.get("ig_full_name", ""),
                "bio": ld.get("ig_bio", ""),
                "website": ld.get("ig_website", ""),
                "ig_category": ld.get("ig_category", ""),
                "followers": ld.get("ig_follower_count", 0),
                "following": ld.get("ig_following_count", 0),
                "is_private": ld.get("ig_is_private", False),
            })

        prompt = BATCH_SCORING_PROMPT.format(
            leads_json=json.dumps(leads_for_prompt, ensure_ascii=False, indent=1),
            lead_count=len(leads_data),
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()
        # Strip markdown code fences if present
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1] if "\n" in response_text else response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()

        results = json.loads(response_text)
        if not isinstance(results, list):
            raise ValueError(f"Expected JSON array, got {type(results).__name__}")
        return results

    def _score_batch_safe(self, leads_data: list[dict]) -> list[tuple[str, dict | None]]:
        """Thread-safe batch scoring. Returns list of (username, result_or_None)."""
        usernames = [ld.get("ig_username", "unknown") for ld in leads_data]
        try:
            results = self.score_batch(leads_data)
            # Map results by username
            result_map = {r.get("username", ""): r for r in results}
            output = []
            for username in usernames:
                if username in result_map:
                    logger.info(f"Scored lead @{username}: {result_map[username].get('score', 0)}")
                    output.append((username, result_map[username]))
                else:
                    logger.warning(f"No score returned for @{username} in batch response")
                    output.append((username, None))
            return output
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from Claude for batch of {len(leads_data)}: {e}")
            return [(u, None) for u in usernames]
        except Exception as e:
            logger.error(f"Error scoring batch of {len(leads_data)}: {type(e).__name__}: {e}")
            return [(u, None) for u in usernames]

    async def score_leads_batch(
        self, lead_ids: list[str], db: AsyncSession,
        progress_callback=None,
    ) -> list[str]:
        """Score leads in batches (multiple leads per API call). Returns list of scored lead_ids."""
        result = await db.execute(
            select(Lead).where(Lead.id.in_(lead_ids), Lead.status == "scraped")
        )
        leads = result.scalars().all()

        if not leads:
            logger.warning(f"No leads with status='scraped' found for {len(lead_ids)} IDs")
            return []

        logger.info(f"Found {len(leads)} scraped leads to score out of {len(lead_ids)} IDs")

        # Prepare lead data — skip leads with no useful data (saves API calls)
        lead_data_map: dict[str, tuple] = {}  # username -> (lead, lead_data, cleaned_bio)
        all_lead_data: list[dict] = []
        skipped_count = 0
        for lead in leads:
            has_bio = bool(lead.ig_bio and lead.ig_bio.strip())
            has_followers = bool(lead.ig_follower_count and lead.ig_follower_count > 0)
            has_name = bool(lead.ig_full_name and lead.ig_full_name.strip())

            if not has_bio and not has_followers and not has_name:
                # No data to score — mark as scored with 0
                lead.score = 0
                lead.score_reason = "No profile data available (empty bio, no followers)"
                lead.lead_category = "other"
                lead.status = "scored"
                lead.scored_at = datetime.now(timezone.utc)
                skipped_count += 1
                continue

            cleaned_bio = clean_bio(lead.ig_bio)
            lead_data = {
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name,
                "ig_bio": cleaned_bio,
                "ig_website": lead.ig_website,
                "ig_category": lead.ig_category,
                "ig_follower_count": lead.ig_follower_count,
                "ig_following_count": lead.ig_following_count,
                "ig_is_private": lead.ig_is_private,
            }
            lead_data_map[lead.ig_username] = (lead, lead_data, cleaned_bio)
            all_lead_data.append(lead_data)

        if skipped_count:
            logger.info(f"Skipped {skipped_count} leads with no profile data (auto-scored 0)")

        # Split into batches
        batches = [all_lead_data[i:i + BATCH_SIZE] for i in range(0, len(all_lead_data), BATCH_SIZE)]
        logger.info(f"Scoring {len(leads)} leads in {len(batches)} batches of ~{BATCH_SIZE} (max {MAX_PARALLEL_BATCHES} parallel)")

        scored_ids = []
        completed_count = 0

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_BATCHES) as executor:
            futures = {
                executor.submit(self._score_batch_safe, batch): i
                for i, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                batch_idx = futures[future]
                batch_results = future.result()
                logger.info(f"Batch {batch_idx + 1}/{len(batches)} completed with {len(batch_results)} results")

                for username, score_result in batch_results:
                    completed_count += 1

                    if progress_callback:
                        try:
                            progress_callback(completed_count, len(leads), username)
                        except Exception as e:
                            logger.warning(f"Progress callback failed: {e}")

                    if score_result is None:
                        continue

                    if username not in lead_data_map:
                        logger.warning(f"Score returned for unknown username @{username}")
                        continue

                    lead, _, cleaned_bio = lead_data_map[username]
                    lead.score = score_result.get("score", 0)
                    lead.score_reason = score_result.get("reason", "")
                    lead.lead_category = score_result.get("category", "other")
                    lead.ig_bio_clean = score_result.get("bio_clean") or cleaned_bio
                    lead.status = "scored"
                    lead.scored_at = datetime.now(timezone.utc)
                    scored_ids.append(str(lead.id))

        await db.flush()
        logger.info(f"Batch scoring complete: {len(scored_ids)}/{len(leads)} leads scored")
        return scored_ids


scoring_service = ScoringService()
