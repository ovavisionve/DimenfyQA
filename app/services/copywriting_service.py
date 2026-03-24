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

# Batch size for DM generation
DM_BATCH_SIZE = 5
# Max parallel batch API calls
MAX_PARALLEL_BATCHES = 3

SINGLE_DM_PROMPT = """Eres un copywriter experto en cold DMs de Instagram para {client_business_type}.

## Información del lead:
- Nombre: {full_name}
- Username: {username}
- Bio: {bio}
- Categoría: {category}
- Website: {website}
- Research: {research_data}

## Servicio que ofrecemos:
{client_service_description}

{content_analysis_context}

## Formato de cada DM:
[Saludo personal con nombre si disponible]
[Cumplido específico basado en research/bio — 1 oración]
[Transición natural a nuestra propuesta de valor — 1-2 oraciones]
[Pregunta de cierre suave — 1 oración]

## Reglas:
1. SOLO texto plano, sin formateo
2. Máximo 4-5 oraciones por DM
3. Nunca uses palabras que suenen a IA: "journey", "game-changer", "impressive", "amplify", "transformation"
4. Tono: {tone_instruction}
5. Si no sabes el nombre, omítelo
6. NUNCA pidas una llamada o reunión directamente
7. No uses paréntesis, comillas dobles, ni caracteres especiales
8. Evita: emojis, exclamaciones excesivas, ALL CAPS
9. El DM debe sentirse como si un amigo profesional te escribiera
10. Usa los pain points y propuestas de valor del análisis de contenido para hacer el DM relevante

## Output:
Responde SOLO en JSON válido, sin markdown ni backticks:
{{
  "dm_a": "<texto del DM variante A>",
  "dm_b": "<texto del DM variante B con ángulo diferente>"
}}"""

BATCH_DM_PROMPT = """Eres un copywriter experto en cold DMs de Instagram para {client_business_type}.

## Servicio que ofrecemos:
{client_service_description}

{content_analysis_context}

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
4. Tono: {tone_instruction}
5. Si no sabes el nombre, omítelo
6. NUNCA pidas una llamada o reunión directamente
7. No uses paréntesis, comillas dobles, ni caracteres especiales
8. Evita: emojis, exclamaciones excesivas, ALL CAPS
9. El DM debe sentirse como si un amigo profesional te escribiera
10. Cada DM debe ser ÚNICO y personalizado al lead
11. Conecta los pain points del lead con las propuestas de valor del análisis de contenido

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


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from API response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


class CopywritingService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _call_claude(self, prompt: str, max_tokens: int = 4096) -> str:
        """Make a Claude API call and return the text response."""
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    @staticmethod
    def _build_content_context(client_config: dict) -> tuple[str, str]:
        """
        Build content analysis context and tone instruction from client config.
        Returns (content_analysis_context, tone_instruction).
        """
        content_analysis = client_config.get("content_analysis")
        tone_instruction = "conversación natural entre profesionales, no formal ni robótico"

        if not content_analysis or "error" in content_analysis:
            return ("", tone_instruction)

        parts = []

        summary = content_analysis.get("business_summary", "")
        if summary:
            parts.append(f"**Resumen del negocio**: {summary}")

        value_props = content_analysis.get("value_propositions", [])
        if value_props:
            props_text = "\n".join(f"  - {vp}" for vp in value_props)
            parts.append(f"**Propuestas de valor clave**:\n{props_text}")

        target = content_analysis.get("target_audience", "")
        if target:
            parts.append(f"**Audiencia ideal**: {target}")

        differentiators = content_analysis.get("key_differentiators", [])
        if differentiators:
            diff_text = "\n".join(f"  - {d}" for d in differentiators)
            parts.append(f"**Diferenciadores**:\n{diff_text}")

        social_proof = content_analysis.get("social_proof", [])
        if social_proof:
            sp_text = "\n".join(f"  - {sp}" for sp in social_proof)
            parts.append(f"**Prueba social**:\n{sp_text}")

        pain_points = content_analysis.get("pain_points_addressed", [])
        if pain_points:
            pp_text = "\n".join(f"  - {pp}" for pp in pain_points)
            parts.append(f"**Problemas que resolvemos**:\n{pp_text}")

        cta = content_analysis.get("call_to_action_hints", "")
        if cta:
            parts.append(f"**Acción deseada del prospecto**: {cta}")

        # Extract tone from analysis
        tone = content_analysis.get("tone_style", "")
        if tone:
            tone_instruction = f"{tone} — mantenlo natural y humano, nunca robótico"

        context = ""
        if parts:
            context = "## Análisis de contenido del cliente (extraído por IA de videos/imágenes/web del cliente):\n" + "\n".join(parts)
            context += "\n\nUSA esta información para crear DMs que conecten naturalmente con lo que el lead necesita."

        return (context, tone_instruction)

    def generate_single_dm(self, lead_data: dict, client_config: dict) -> tuple[str | None, str | None]:
        """Generate DM for a single lead. Returns (dm_a, dm_b) or (None, None) on failure."""
        username = lead_data.get("ig_username", "unknown")
        content_context, tone = self._build_content_context(client_config)
        try:
            prompt = SINGLE_DM_PROMPT.format(
                full_name=lead_data.get("ig_full_name", ""),
                username=username,
                bio=lead_data.get("ig_bio_clean") or lead_data.get("ig_bio", ""),
                category=lead_data.get("lead_category", ""),
                website=lead_data.get("ig_website", ""),
                research_data=lead_data.get("research_data", "No research available"),
                client_business_type=client_config.get("business_type", "B2B automation"),
                client_service_description=client_config.get(
                    "service_description", "B2B lead generation and automation services"
                ),
                content_analysis_context=content_context,
                tone_instruction=tone,
            )
            raw = self._call_claude(prompt, max_tokens=1024)
            result = json.loads(_strip_code_fences(raw))
            dm_a = result.get("dm_a")
            dm_b = result.get("dm_b")
            if dm_a:
                logger.info(f"Generated DM for @{username} (individual fallback)")
            return (dm_a, dm_b)
        except Exception as e:
            logger.error(f"Individual DM generation failed for @{username}: {type(e).__name__}: {e}")
            return (None, None)

    def generate_dms_batch(self, leads_data: list[dict], client_config: dict) -> list[dict]:
        """Generate DMs for a batch of leads in a single API call."""
        content_context, tone = self._build_content_context(client_config)

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
            content_analysis_context=content_context,
            tone_instruction=tone,
        )

        raw = self._call_claude(prompt, max_tokens=8192)
        results = json.loads(_strip_code_fences(raw))
        if not isinstance(results, list):
            raise ValueError(f"Expected JSON array, got {type(results).__name__}")
        return results

    def _generate_dms_batch_safe(self, leads_data: list[dict], client_config: dict) -> list[tuple[str, str | None, str | None]]:
        """Thread-safe batch DM generation with individual fallback."""
        usernames = [ld.get("ig_username", "unknown") for ld in leads_data]
        output = []

        # Try batch first
        try:
            results = self.generate_dms_batch(leads_data, client_config)
            result_map = {r.get("username", ""): r for r in results}
            failed_leads = []

            for i, username in enumerate(usernames):
                if username in result_map:
                    r = result_map[username]
                    logger.info(f"Generated DMs for @{username} (batch)")
                    output.append((username, r.get("dm_a"), r.get("dm_b")))
                else:
                    logger.warning(f"No DM for @{username} in batch — will retry individually")
                    failed_leads.append((i, username, leads_data[i]))

            # Retry missing leads individually
            for i, username, lead_data in failed_leads:
                dm_a, dm_b = self.generate_single_dm(lead_data, client_config)
                output.append((username, dm_a, dm_b))

            return output

        except Exception as e:
            logger.error(f"Batch DM failed ({type(e).__name__}: {e}) — falling back to individual calls")
            # Fallback: generate each DM individually
            for i, username in enumerate(usernames):
                dm_a, dm_b = self.generate_single_dm(leads_data[i], client_config)
                output.append((username, dm_a, dm_b))
            return output

    async def write_dms_batch(
        self, lead_ids: list[str], db: AsyncSession,
        progress_callback=None,
    ) -> list[str]:
        """Generate DMs for leads with score >= threshold using batch API calls with individual fallback."""
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
            logger.warning(f"No leads with status in (scored, researched) and score >= {threshold} found")
            return []

        logger.info(f"Found {len(leads)} leads with score >= {threshold} for DM generation")

        # Get client config + campaign content analysis
        first_lead = leads[0]
        client_result = await db.execute(
            select(Client).where(Client.id == first_lead.client_id)
        )
        client = client_result.scalar_one_or_none()

        # Load campaign content analysis
        from app.models.campaign import Campaign
        campaign_result = await db.execute(
            select(Campaign).where(Campaign.id == first_lead.campaign_id)
        )
        campaign = campaign_result.scalar_one_or_none()
        content_analysis = (campaign.settings or {}).get("content_analysis") if campaign else None

        client_config = {
            "business_type": client.business_type if client else "B2B automation",
            "service_description": (client.settings or {}).get(
                "service_description",
                "B2B lead generation and automation services",
            ) if client else "B2B lead generation and automation services",
            "content_analysis": content_analysis,
        }

        if content_analysis:
            logger.info("Using campaign content analysis for enriched DM generation")

        # Prepare lead data
        lead_data_map: dict[str, tuple] = {}
        all_lead_data: list[dict] = []
        for lead in leads:
            research = lead.research_data or "No research available"

            # Enrich with post analysis personalization hooks
            post_analysis = lead.ig_post_analysis
            if post_analysis:
                hooks = post_analysis.get("personalization_hooks", [])
                interests = post_analysis.get("interests", [])
                approach = post_analysis.get("best_approach", "")
                if hooks:
                    research += f"\nPersonalization hooks from posts: {', '.join(hooks[:3])}"
                if interests:
                    research += f"\nInterests from content: {', '.join(interests[:4])}"
                if approach:
                    research += f"\nBest approach: {approach}"

            lead_data = {
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name,
                "ig_bio": lead.ig_bio,
                "ig_bio_clean": lead.ig_bio_clean,
                "ig_website": lead.ig_website,
                "lead_category": lead.lead_category,
                "research_data": research,
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
                logger.info(f"DM batch {batch_idx + 1}/{len(batches)} completed with {len(batch_results)} results")

                for username, dm_a, dm_b in batch_results:
                    completed_count += 1

                    if progress_callback:
                        try:
                            progress_callback(completed_count, len(leads), username)
                        except Exception:
                            pass

                    if dm_a is None:
                        logger.warning(f"No DM generated for @{username} (both batch and individual failed)")
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
