import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead

logger = logging.getLogger(__name__)

# Max parallel research API calls
MAX_PARALLEL_RESEARCH = 8

RESEARCH_PROMPT = """Busca información sobre esta persona/negocio que pueda usarse para escribir un DM personalizado en Instagram.

Nombre: {full_name}
Username IG: {username}
Website: {website}
Bio: {bio}
Categoría: {category}

{content_context}

Busca:
1. Logros recientes o noticias
2. Información personal relevante (ciudades, intereses)
3. Tipo de negocio y qué venden
4. Cualquier dato que permita un mensaje personal y auténtico
5. Conexiones potenciales entre el lead y nuestro servicio

Responde en un párrafo corto y conciso con los datos más útiles."""


class ResearchService:
    def __init__(self):
        self.google_api_key = settings.GOOGLE_API_KEY
        self.perplexity_api_key = settings.PERPLEXITY_API_KEY

    @property
    def _use_google(self) -> bool:
        return bool(self.google_api_key)

    async def research_lead(self, lead_data: dict, content_analysis: dict | None = None) -> str:
        """Research a single lead using Google Gemini or Perplexity API."""
        # Build content context from campaign content analysis
        content_context = ""
        if content_analysis and "error" not in content_analysis:
            summary = content_analysis.get("business_summary", "")
            audience = content_analysis.get("target_audience", "")
            pain_points = ", ".join(content_analysis.get("pain_points_addressed", []))
            if summary:
                content_context = (
                    f"## Contexto de nuestro servicio (para encontrar conexiones relevantes):\n"
                    f"Nuestro negocio: {summary}\n"
                    f"Audiencia ideal: {audience}\n"
                    f"Problemas que resolvemos: {pain_points}\n"
                    f"Busca conexiones entre este lead y lo que ofrecemos."
                )

        prompt = RESEARCH_PROMPT.format(
            full_name=lead_data.get("ig_full_name", ""),
            username=lead_data.get("ig_username", ""),
            website=lead_data.get("ig_website", ""),
            bio=lead_data.get("ig_bio_clean") or lead_data.get("ig_bio", ""),
            category=lead_data.get("lead_category", ""),
            content_context=content_context,
        )

        if self._use_google:
            return await self._research_with_gemini(prompt)
        return await self._research_with_perplexity(prompt)

    async def _research_with_gemini(self, prompt: str) -> str:
        """Research using Google Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.google_api_key}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 500,
                    },
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _research_with_perplexity(self, prompt: str) -> str:
        """Research using Perplexity API (fallback)."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    @property
    def _has_api_key(self) -> bool:
        """Check if any research API key is properly configured."""
        if self.google_api_key and len(self.google_api_key.strip()) >= 20:
            return True
        if self.perplexity_api_key and len(self.perplexity_api_key.strip()) >= 20:
            return True
        return False

    async def research_leads_batch(
        self, lead_ids: list[str], db: AsyncSession,
        progress_callback=None,
    ) -> list[str]:
        """Research leads with score >= threshold. Returns list of researched lead_ids."""
        threshold = settings.RESEARCH_SCORE_THRESHOLD

        result = await db.execute(
            select(Lead).where(
                Lead.id.in_(lead_ids),
                Lead.status == "scored",
                Lead.score >= threshold,
            )
        )
        leads = result.scalars().all()

        # Load campaign content analysis if available
        content_analysis = None
        if leads:
            from app.models.campaign import Campaign
            campaign_result = await db.execute(
                select(Campaign).where(Campaign.id == leads[0].campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()
            if campaign:
                content_analysis = (campaign.settings or {}).get("content_analysis")
                if content_analysis:
                    logger.info("Using campaign content analysis for enriched research")

        # If no research API key is configured, skip research and mark as researched
        if not self._has_api_key:
            logger.warning("No research API key configured — skipping research, marking %d leads as researched", len(leads))
            researched_ids = []
            for lead in leads:
                lead.status = "researched"
                lead.researched_at = datetime.now(timezone.utc)
                researched_ids.append(str(lead.id))
            await db.flush()
            return researched_ids

        # Research leads in parallel using asyncio semaphore
        logger.info(f"Researching {len(leads)} leads in parallel (max {MAX_PARALLEL_RESEARCH} concurrent)")
        semaphore = asyncio.Semaphore(MAX_PARALLEL_RESEARCH)

        completed_count = 0

        async def _research_one(lead):
            nonlocal completed_count
            async with semaphore:
                lead_data = {
                    "ig_username": lead.ig_username,
                    "ig_full_name": lead.ig_full_name,
                    "ig_bio": lead.ig_bio,
                    "ig_bio_clean": lead.ig_bio_clean,
                    "ig_website": lead.ig_website,
                    "lead_category": lead.lead_category,
                }

                # Auto-analyze lead's posts with Gemini if available
                if lead.ig_posts and self.google_api_key:
                    try:
                        from app.services.content_analysis_service import content_analysis_service
                        post_analysis = await content_analysis_service.analyze_lead_content(
                            username=lead.ig_username,
                            full_name=lead.ig_full_name or "",
                            bio=lead.ig_bio_clean or lead.ig_bio or "",
                            posts_data=lead.ig_posts,
                        )
                        if post_analysis:
                            lead.ig_post_analysis = post_analysis
                            logger.info(f"Analyzed {len(lead.ig_posts)} posts for @{lead.ig_username}")
                    except Exception as e:
                        logger.warning(f"Post analysis failed for @{lead.ig_username}: {e}")

                try:
                    research_text = await self.research_lead(lead_data, content_analysis=content_analysis)

                    # Enrich research with post analysis if available
                    if lead.ig_post_analysis:
                        hooks = lead.ig_post_analysis.get("personalization_hooks", [])
                        approach = lead.ig_post_analysis.get("best_approach", "")
                        if hooks or approach:
                            research_text += f"\n\nAnálisis de posts recientes:"
                            if hooks:
                                research_text += f"\nHooks de personalización: {', '.join(hooks[:3])}"
                            if approach:
                                research_text += f"\nMejor ángulo: {approach}"

                    lead.research_data = research_text
                    lead.research_summary = research_text[:500]
                    logger.info(f"Researched lead {lead.ig_username}")
                except Exception as e:
                    logger.error(f"Error researching lead {lead.ig_username}: {type(e).__name__}: {e}")
                # Mark as researched even on failure to not block pipeline
                lead.status = "researched"
                lead.researched_at = datetime.now(timezone.utc)
                completed_count += 1
                if progress_callback:
                    try:
                        result = progress_callback(completed_count, len(leads), lead.ig_username)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass
                return str(lead.id)

        researched_ids = await asyncio.gather(*[_research_one(lead) for lead in leads])

        await db.flush()
        logger.info(f"Parallel research complete: {len(researched_ids)}/{len(leads)} leads researched")
        return list(researched_ids)


research_service = ResearchService()
