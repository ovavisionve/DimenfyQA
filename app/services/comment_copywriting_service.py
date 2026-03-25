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

COMMENT_BATCH_SIZE = 5
MAX_PARALLEL_BATCHES = 3

SINGLE_COMMENT_PROMPT = """Eres un experto en engagement de Instagram. Tu trabajo es escribir comentarios naturales y relevantes en publicaciones de leads potenciales.

## Información del lead:
- Username: {username}
- Nombre: {full_name}
- Bio: {bio}
- Categoría: {category}

## Post a comentar:
- Caption: {post_caption}
- Tipo: {post_type}
- Likes: {post_likes}

## Nuestro negocio:
{client_service_description}

## Reglas:
1. El comentario debe ser CORTO (1-2 oraciones, máximo 150 caracteres)
2. Debe parecer un comentario genuino de alguien interesado en el contenido
3. NO vendas ni promociones nada — solo engagement auténtico
4. Comenta sobre el CONTENIDO del post, no sobre el lead en general
5. Usa un tono casual y natural, como un seguidor real
6. NO uses emojis excesivos (máximo 1 emoji, preferible ninguno)
7. NO uses hashtags
8. NO pidas nada (ni llamadas, ni reuniones, ni visitas al perfil)
9. Varía entre: cumplido específico, pregunta relevante, opinión relacionada
10. NUNCA menciones que eres un bot o empresa
11. Escribe en el idioma del post (si el caption es en español, comenta en español)

## Output:
Responde SOLO en JSON válido, sin markdown ni backticks:
{{
  "comment_a": "<comentario variante A>",
  "comment_b": "<comentario variante B con ángulo diferente>"
}}"""

BATCH_COMMENT_PROMPT = """Eres un experto en engagement de Instagram. Escribe comentarios naturales para publicaciones de estos leads.

## Nuestro negocio:
{client_service_description}

## Leads y sus posts:
{leads_json}

## Reglas:
1. Comentario CORTO (1-2 oraciones, máximo 150 caracteres cada uno)
2. Debe parecer un comentario genuino de alguien interesado
3. NO vendas ni promociones nada — solo engagement auténtico
4. Comenta sobre el CONTENIDO del post específico
5. Tono casual y natural, como un seguidor real
6. Máximo 1 emoji por comentario, preferible ninguno
7. NO uses hashtags ni pidas nada
8. Varía el estilo: cumplido, pregunta relevante, opinión
9. NUNCA menciones que eres bot o empresa
10. Escribe en el idioma del caption del post

## Output:
Responde SOLO un JSON array válido, sin markdown ni backticks:
[
  {{
    "username": "<ig_username exacto>",
    "comment_a": "<comentario variante A>",
    "comment_b": "<comentario variante B>"
  }}
]

IMPORTANTE: Devuelve EXACTAMENTE {lead_count} elementos."""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


class CommentCopywritingService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _call_claude(self, prompt: str, max_tokens: int = 4096) -> str:
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    @staticmethod
    def _pick_best_post(posts: list[dict]) -> dict | None:
        """Pick the best post to comment on: most recent with decent engagement."""
        if not posts:
            return None
        # Prefer posts with captions (more context for comment generation)
        with_caption = [p for p in posts if p.get("caption")]
        candidates = with_caption if with_caption else posts
        # Sort by engagement (likes + comments), take most engaging
        candidates.sort(key=lambda p: (p.get("likesCount", 0) + p.get("commentsCount", 0)), reverse=True)
        return candidates[0]

    def generate_single_comment(self, lead_data: dict, client_config: dict) -> tuple[str | None, str | None, str | None]:
        """Generate comment for a single lead. Returns (comment_a, comment_b, shortcode) or (None, None, None)."""
        username = lead_data.get("ig_username", "unknown")
        posts = lead_data.get("ig_posts") or []
        post = self._pick_best_post(posts)
        if not post:
            logger.warning(f"No posts available for @{username}, skipping comment generation")
            return (None, None, None)

        try:
            prompt = SINGLE_COMMENT_PROMPT.format(
                username=username,
                full_name=lead_data.get("ig_full_name", ""),
                bio=lead_data.get("ig_bio_clean") or lead_data.get("ig_bio", ""),
                category=lead_data.get("lead_category", ""),
                post_caption=(post.get("caption") or "")[:300],
                post_type=post.get("type", "Post"),
                post_likes=post.get("likesCount", 0),
                client_service_description=client_config.get(
                    "service_description", "B2B lead generation and automation services"
                ),
            )
            raw = self._call_claude(prompt, max_tokens=512)
            result = json.loads(_strip_code_fences(raw))
            comment_a = result.get("comment_a")
            comment_b = result.get("comment_b")
            shortcode = post.get("shortCode", "")
            if comment_a:
                logger.info(f"Generated comment for @{username} on post {shortcode}")
            return (comment_a, comment_b, shortcode)
        except Exception as e:
            logger.error(f"Comment generation failed for @{username}: {type(e).__name__}: {e}")
            return (None, None, None)

    def generate_comments_batch(self, leads_data: list[dict], client_config: dict) -> list[dict]:
        """Generate comments for a batch of leads in a single API call."""
        leads_for_prompt = []
        shortcode_map = {}

        for ld in leads_data:
            posts = ld.get("ig_posts") or []
            post = self._pick_best_post(posts)
            if not post:
                continue
            username = ld.get("ig_username", "")
            shortcode_map[username] = post.get("shortCode", "")
            leads_for_prompt.append({
                "username": username,
                "name": ld.get("ig_full_name", ""),
                "bio": (ld.get("ig_bio_clean") or ld.get("ig_bio", ""))[:200],
                "category": ld.get("lead_category", ""),
                "post_caption": (post.get("caption") or "")[:300],
                "post_type": post.get("type", "Post"),
                "post_likes": post.get("likesCount", 0),
            })

        if not leads_for_prompt:
            return []

        prompt = BATCH_COMMENT_PROMPT.format(
            leads_json=json.dumps(leads_for_prompt, ensure_ascii=False, indent=1),
            lead_count=len(leads_for_prompt),
            client_service_description=client_config.get(
                "service_description", "B2B lead generation and automation services"
            ),
        )

        raw = self._call_claude(prompt, max_tokens=4096)
        results = json.loads(_strip_code_fences(raw))
        if not isinstance(results, list):
            raise ValueError(f"Expected JSON array, got {type(results).__name__}")

        # Attach shortcodes
        for r in results:
            r["shortcode"] = shortcode_map.get(r.get("username", ""), "")
        return results

    def _generate_comments_batch_safe(self, leads_data: list[dict], client_config: dict) -> list[tuple[str, str | None, str | None, str]]:
        """Thread-safe batch comment generation with individual fallback.
        Returns list of (username, comment_a, comment_b, shortcode).
        """
        output = []

        try:
            results = self.generate_comments_batch(leads_data, client_config)
            result_map = {r.get("username", ""): r for r in results}
            failed_leads = []

            for i, ld in enumerate(leads_data):
                username = ld.get("ig_username", "unknown")
                if username in result_map:
                    r = result_map[username]
                    output.append((username, r.get("comment_a"), r.get("comment_b"), r.get("shortcode", "")))
                else:
                    failed_leads.append((i, username, ld))

            for i, username, ld in failed_leads:
                ca, cb, sc = self.generate_single_comment(ld, client_config)
                output.append((username, ca, cb, sc or ""))

            return output

        except Exception as e:
            logger.error(f"Batch comment generation failed ({type(e).__name__}: {e}) — falling back to individual")
            for ld in leads_data:
                username = ld.get("ig_username", "unknown")
                ca, cb, sc = self.generate_single_comment(ld, client_config)
                output.append((username, ca, cb, sc or ""))
            return output

    async def write_comments_batch(
        self, lead_ids: list[str], db: AsyncSession,
        progress_callback=None,
    ) -> list[str]:
        """Generate comments for leads with score >= threshold and posts available."""
        threshold = settings.COMMENT_SCORE_THRESHOLD

        result = await db.execute(
            select(Lead).where(
                Lead.id.in_(lead_ids),
                Lead.score >= threshold,
                Lead.ig_posts.isnot(None),
                Lead.comment_message.is_(None),  # Don't regenerate
            )
        )
        leads = result.scalars().all()

        if not leads:
            logger.warning(f"No leads with score >= {threshold} and posts available for comment generation")
            return []

        logger.info(f"Found {len(leads)} leads for comment generation")

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
        lead_data_map: dict[str, Lead] = {}
        all_lead_data: list[dict] = []
        for lead in leads:
            lead_data = {
                "ig_username": lead.ig_username,
                "ig_full_name": lead.ig_full_name,
                "ig_bio": lead.ig_bio,
                "ig_bio_clean": lead.ig_bio_clean,
                "lead_category": lead.lead_category,
                "ig_posts": lead.ig_posts if isinstance(lead.ig_posts, list) else [],
            }
            lead_data_map[lead.ig_username] = lead
            all_lead_data.append(lead_data)

        # Split into batches
        batches = [all_lead_data[i:i + COMMENT_BATCH_SIZE] for i in range(0, len(all_lead_data), COMMENT_BATCH_SIZE)]
        logger.info(f"Generating comments in {len(batches)} batches of ~{COMMENT_BATCH_SIZE}")

        comment_ready_ids = []
        completed_count = 0

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_BATCHES) as executor:
            futures = {
                executor.submit(self._generate_comments_batch_safe, batch, client_config): i
                for i, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                batch_results = future.result()

                for username, comment_a, comment_b, shortcode in batch_results:
                    completed_count += 1

                    if progress_callback:
                        try:
                            progress_callback(completed_count, len(leads), username)
                        except Exception:
                            pass

                    if comment_a is None:
                        continue

                    if username not in lead_data_map:
                        continue

                    lead = lead_data_map[username]
                    lead.comment_message = comment_a
                    if comment_b:
                        lead.comment_variant_b = comment_b
                    lead.comment_status = "pending"
                    lead.commented_post_shortcode = shortcode
                    comment_ready_ids.append(str(lead.id))

        await db.flush()
        logger.info(f"Comment generation complete: {len(comment_ready_ids)}/{len(leads)} comments generated")
        return comment_ready_ids


comment_copywriting_service = CommentCopywritingService()
