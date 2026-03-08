import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.models.client import Client

logger = logging.getLogger(__name__)

# Batch size for DM generation (fewer than scoring because output is longer)
DM_BATCH_SIZE = 5
# Max parallel batch API calls
MAX_PARALLEL_BATCHES = 3

BATCH_DM_PROMPT = """Eres un copywriter experto en cold DMs de Instagram para {client_business_type}.

## Servicio que ofrecemos:
{client_service_description}

## Leads para generar DMs:
{leads_json}

## Formato de cada DM:
[Saludo personal con nombre si disponible]
[Cumplido específico basado en research/bio — 1 oración]
[Transición natural a nuestra propuesta de valor — 1-2 oraciones]
[Pregunta de cierre suave — 1 oración]

## Reglas:
1. SOLO texto plano, sin formateo
2. Máximo 4-5 oraciones por DM
3. Nunca uses palabras que suenen a IA: "journey", "game-changer", "impressive", "amplify", "transformation"
4. Tono: conversación natural entre profesionales, no formal ni robótico
5. Si no sabes el nombre, omítelo
6. NUNCA pidas una llamada o reunión directamente
7. No uses paréntesis, comillas dobles, ni caracteres especiales
8. Evita: emojis, exclamaciones excesivas, ALL CAPS
9. El DM debe sentirse como si un amigo profesional te escribiera
10. Cada DM debe ser ÚNICO y personalizado al lead

## Output:
Responde SOLO un JSON array válido, sin markdown ni backticks. Para cada lead genera 2 variantes (A/B test):
[
  {{
    "username": "<ig_username exacto>",
    "dm_a": "<texto del DM variante A>",
    "dm_b": "<texto del DM variante B con ángulo diferente>"
  }}
]

IMPORTANTE: Devuelve EXACTAMENTE {lead_count} elementos, uno por cada lead."""


class CopywritingService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def generate_dms_batch(self, leads_data: list[dict], client_config: dict) -> list[dict]:
        """Generate DMs for a batch of leads in a single API call."""
        leads_for_prompt = []
        for ld in leads_data:
            leads_for_prompt.append({
                "username": ld.get("ig_username", ""),
                "name": ld.get("ig_full_name", ""),
                "bio": ld.get("ig_bio_clean") or ld.get("ig_bio", ""),
                "category": ld.get("lead_category", ""),
                "website": ld.get("ig_website", ""),
                "research": ld.get("research_data", "No research available"),
            })

        prompt = BATCH_DM_PROMPT.format(
            leads_json=json.dumps(leads_for_prompt, ensure_ascii=False, indent=1),
            lead_count=len(leads_data),
            client_business_type=client_config.get("business_type", "B2B automation"),
            client_service_description=client_config.get(
                "service_description", "B2B lead generation and automation services"
            ),
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1] if "\n" in response_text else response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()

        results = json.loads(response_text)
        if not isinstance(results, list):
            raise ValueError(f"Expected JSON array, got {type(results).__name__}")
        return results

    def _generate_dms_batch_safe(self, leads_data: list[dict], client_config: dict) -> list[tuple[str, str | None, str | None]]:
        """Thread-safe batch DM generation. Returns list of (username, dm_a, dm_b)."""
        usernames = [ld.get("ig_username", "unknown") for ld in leads_data]
        try:
            results = self.generate_dms_batch(leads_data, client_config)
            result_map = {r.get("username", ""): r for r in results}
            output = []
            for username in usernames:
                if username in result_map:
                    r = result_map[username]
                    logger.info(f"Generated DMs for @{username}")
                    output.append((username, r.get("dm_a"), r.get("dm_b")))
                else:
                    logger.warning(f"No DM returned for @{username} in batch")
                    output.append((username, None, None))
            return output
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from Claude for DM batch of {len(leads_data)}: {e}")
            return [(u, None, None) for u in usernames]
        except Exception as e:
            logger.error(f"Error generating DM batch of {len(leads_data)}: {type(e).__name__}: {e}")
            return [(u, None, None) for u in usernames]

    async def write_dms_batch(
        self, lead_ids: list[str], db: AsyncSession,
        progress_callback=None,
    ) -> list[str]:
        """Generate DMs for leads with score >= threshold using batch API calls."""
        threshold = settings.DM_SCORE_THRESHOLD

        result = await db.execute(
            select(Lead).where(
                Lead.id.in_(lead_ids),
                Lead.status.in_(["scored", "researched"]),
                Lead.score >= threshold,
            )
        )
        leads = result.scalars().all()

        if not leads:
            logger.info(f"No leads with score >= {threshold} to generate DMs for")
            return []

        # Get client config
        first_lead = leads[0]
        client_result = await db.execute(
            select(Client).where(Client.id == first_lead.client_id)
        )
        client = client_result.scalar_one_or_none()
        client_config = {
            "business_type": client.business_type if client else "B2B automation",
            "service_description": (client.settings or {}).get(
                "service_description",
                "B2B lead generation and automation services",
            ) if client else "B2B lead generation and automation services",
        }

        # Prepare lead data
        lead_data_map: dict[str, tuple] = {}
        all_lead_data: list[dict] = []
        for lead in leads:
            lead_data = {
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name,
                "ig_bio": lead.ig_bio,
                "ig_bio_clean": lead.ig_bio_clean,
                "ig_website": lead.ig_website,
                "lead_category": lead.lead_category,
                "research_data": lead.research_data or "No research available",
            }
            lead_data_map[lead.ig_username] = (lead, lead_data)
            all_lead_data.append(lead_data)

        # Split into batches
        batches = [all_lead_data[i:i + DM_BATCH_SIZE] for i in range(0, len(all_lead_data), DM_BATCH_SIZE)]
        logger.info(f"Generating DMs for {len(leads)} leads in {len(batches)} batches of ~{DM_BATCH_SIZE}")

        dm_ready_ids = []
        completed_count = 0

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_BATCHES) as executor:
            futures = {
                executor.submit(self._generate_dms_batch_safe, batch, client_config): i
                for i, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                batch_idx = futures[future]
                batch_results = future.result()
                logger.info(f"DM batch {batch_idx + 1}/{len(batches)} completed")

                for username, dm_a, dm_b in batch_results:
                    completed_count += 1

                    if progress_callback:
                        try:
                            progress_callback(completed_count, len(leads), username)
                        except Exception:
                            pass

                    if dm_a is None:
                        continue

                    if username not in lead_data_map:
                        logger.warning(f"DM returned for unknown username @{username}")
                        continue

                    lead, _ = lead_data_map[username]
                    lead.dm_message = dm_a
                    if dm_b:
                        lead.dm_variant_b = dm_b
                    lead.status = "dm_ready"
                    lead.dm_generated_at = datetime.now(timezone.utc)
                    dm_ready_ids.append(str(lead.id))

        await db.flush()
        logger.info(f"Batch DM generation complete: {len(dm_ready_ids)}/{len(leads)} DMs generated")
        return dm_ready_ids


copywriting_service = CopywritingService()
