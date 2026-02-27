import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead

logger = logging.getLogger(__name__)

RESEARCH_PROMPT = """Busca información sobre esta persona/negocio que pueda usarse para escribir un DM personalizado en Instagram.

Nombre: {full_name}
Username IG: {username}
Website: {website}
Bio: {bio}
Categoría: {category}

Busca:
1. Logros recientes o noticias
2. Información personal relevante (ciudades, intereses)
3. Tipo de negocio y qué venden
4. Cualquier dato que permita un mensaje personal y auténtico

Responde en un párrafo corto y conciso con los datos más útiles."""


class ResearchService:
    def __init__(self):
        self.api_key = settings.PERPLEXITY_API_KEY

    async def research_lead(self, lead_data: dict) -> str:
        """Research a single lead using Perplexity API."""
        prompt = RESEARCH_PROMPT.format(
            full_name=lead_data.get("ig_full_name", ""),
            username=lead_data.get("ig_username", ""),
            website=lead_data.get("ig_website", ""),
            bio=lead_data.get("ig_bio_clean") or lead_data.get("ig_bio", ""),
            category=lead_data.get("lead_category", ""),
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
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

    async def research_leads_batch(
        self, lead_ids: list[str], db: AsyncSession
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

        researched_ids = []
        for lead in leads:
            try:
                lead_data = {
                    "ig_username": lead.ig_username,
                    "ig_full_name": lead.ig_full_name,
                    "ig_bio": lead.ig_bio,
                    "ig_bio_clean": lead.ig_bio_clean,
                    "ig_website": lead.ig_website,
                    "lead_category": lead.lead_category,
                }
                research_text = await self.research_lead(lead_data)

                lead.research_data = research_text
                lead.research_summary = research_text[:500]
                lead.status = "researched"
                lead.researched_at = datetime.now(timezone.utc)

                researched_ids.append(str(lead.id))
                logger.info(f"Researched lead {lead.ig_username}")
            except Exception:
                logger.exception(f"Error researching lead {lead.ig_username}")

        await db.flush()
        return researched_ids


research_service = ResearchService()
