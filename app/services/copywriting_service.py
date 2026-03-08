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

# Max parallel API calls for DM generation
MAX_PARALLEL_DMS = 8

COPYWRITING_PROMPT = """Eres un copywriter experto en cold DMs de Instagram para {client_business_type}.

## Información del lead:
- Nombre: {full_name}
- Username: {username}
- Bio: {bio}
- Categoría: {category}
- Website: {website}
- Research: {research_data}

## Servicio que ofrecemos:
{client_service_description}

## Formato del DM:
[Saludo personal con nombre si disponible]
[Cumplido específico basado en research/bio — 1 oración]
[Transición natural a nuestra propuesta de valor — 1-2 oraciones]
[Pregunta de cierre suave — 1 oración]

## Reglas:
1. SOLO texto plano, sin formateo
2. Máximo 4-5 oraciones totales
3. Nunca uses palabras que suenen a IA: "journey", "game-changer", "impressive", "amplify", "transformation"
4. Tono: conversación natural entre profesionales, no formal ni robótico
5. Si no sabes el nombre, omítelo
6. NUNCA pidas una llamada o reunión directamente
7. No uses paréntesis, comillas dobles, ni caracteres especiales
8. Evita: emojis, exclamaciones excesivas, ALL CAPS
9. El DM debe sentirse como si un amigo profesional te escribiera
10. Output SOLO el texto del DM, nada más

## Output:
Responde SOLO con el texto del DM. Sin explicaciones, sin comillas, sin JSON."""

VARIANT_B_PROMPT = """Eres un copywriter experto en cold DMs de Instagram para {client_business_type}.

Necesito una SEGUNDA variante de un DM para A/B testing. Esta variante debe usar un ángulo DIFERENTE al DM original.

## DM original (variante A):
{variant_a}

## Información del lead:
- Nombre: {full_name}
- Username: {username}
- Bio: {bio}
- Categoría: {category}
- Research: {research_data}

## Servicio que ofrecemos:
{client_service_description}

## Instrucciones para la variante B:
- Usa un GANCHO diferente al de la variante A (si A usa cumplido, B usa curiosidad; si A es directo, B es más sutil)
- Mantén las mismas 10 reglas del formato original
- Máximo 4-5 oraciones
- Tono natural, sin palabras de IA
- SOLO texto plano del DM, nada más"""


class CopywritingService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def generate_dm(self, lead_data: dict, client_config: dict) -> str:
        """Generate a personalized DM for a lead using Claude API."""
        prompt = COPYWRITING_PROMPT.format(
            full_name=lead_data.get("ig_full_name", ""),
            username=lead_data.get("ig_username", ""),
            bio=lead_data.get("ig_bio_clean") or lead_data.get("ig_bio", ""),
            category=lead_data.get("lead_category", ""),
            website=lead_data.get("ig_website", ""),
            research_data=lead_data.get("research_data", "No research available"),
            client_business_type=client_config.get("business_type", "B2B automation"),
            client_service_description=client_config.get(
                "service_description", "B2B lead generation and automation services"
            ),
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        return message.content[0].text.strip()

    def generate_dm_variant_b(self, lead_data: dict, client_config: dict, variant_a: str) -> str:
        """Generate variant B of a DM for A/B testing."""
        prompt = VARIANT_B_PROMPT.format(
            variant_a=variant_a,
            full_name=lead_data.get("ig_full_name", ""),
            username=lead_data.get("ig_username", ""),
            bio=lead_data.get("ig_bio_clean") or lead_data.get("ig_bio", ""),
            category=lead_data.get("lead_category", ""),
            research_data=lead_data.get("research_data", "No research available"),
            client_business_type=client_config.get("business_type", "B2B automation"),
            client_service_description=client_config.get(
                "service_description", "B2B lead generation and automation services"
            ),
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        return message.content[0].text.strip()

    def _generate_dm_safe(self, lead_data: dict, client_config: dict) -> tuple[str, str | None, str | None]:
        """Thread-safe DM generation. Returns (username, variant_a, variant_b)."""
        username = lead_data.get("ig_username", "unknown")
        try:
            dm_text = self.generate_dm(lead_data, client_config)
            dm_variant_b = None
            try:
                dm_variant_b = self.generate_dm_variant_b(lead_data, client_config, dm_text)
            except Exception:
                logger.warning(f"Could not generate variant B for {username}, using only variant A")
            logger.info(f"Generated DM for lead {username}")
            return (username, dm_text, dm_variant_b)
        except Exception:
            logger.exception(f"Error generating DM for lead {username}")
            return (username, None, None)

    async def write_dms_batch(
        self, lead_ids: list[str], db: AsyncSession
    ) -> list[str]:
        """Generate DMs for leads with score >= threshold in parallel. Returns list of dm-ready lead_ids."""
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
            return []

        # Get client config (same for all leads in a campaign)
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

        # Prepare lead data map
        lead_data_map: dict[str, tuple] = {}
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

        # Generate DMs in parallel
        logger.info(f"Generating DMs for {len(leads)} leads in parallel (max {MAX_PARALLEL_DMS} concurrent)")
        dm_ready_ids = []

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_DMS) as executor:
            futures = {
                executor.submit(self._generate_dm_safe, data[1], client_config): username
                for username, data in lead_data_map.items()
            }
            for future in as_completed(futures):
                username = futures[future]
                _, dm_text, dm_variant_b = future.result()
                if dm_text is None:
                    continue

                lead, _ = lead_data_map[username]
                lead.dm_message = dm_text
                if dm_variant_b:
                    lead.dm_variant_b = dm_variant_b
                lead.status = "dm_ready"
                lead.dm_generated_at = datetime.now(timezone.utc)
                dm_ready_ids.append(str(lead.id))

        await db.flush()
        logger.info(f"Parallel DM generation complete: {len(dm_ready_ids)}/{len(leads)} DMs generated")
        return dm_ready_ids


copywriting_service = CopywritingService()
