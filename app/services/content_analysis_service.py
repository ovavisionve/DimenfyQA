"""
Content Analysis Service — Gemini Multimodal Analysis

Analyzes client-provided content (videos, images, URLs, text) to extract
value propositions, key selling points, and context for hyper-personalized DMs.

Also analyzes lead content (posts, reels, stories) when available from scraping.

This is BETTER than just "feed a video to Gemini" because:
1. Supports multiple content types (video, image, webpage, text)
2. Extracts structured business intelligence, not just summaries
3. Creates reusable campaign context that feeds scoring, research, AND copywriting
4. Can also analyze lead-side content for double-context personalization
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign

logger = logging.getLogger(__name__)

# Prompt for analyzing client's content (video/image/url)
CLIENT_CONTENT_ANALYSIS_PROMPT = """Analiza el siguiente contenido del cliente y extrae información estructurada para generar DMs personalizados de Instagram.

El contenido puede ser un video, imagen, página web, o texto descriptivo del negocio/servicio del cliente.

Extrae la siguiente información en JSON:

1. **business_summary**: Resumen de 2-3 oraciones del negocio/servicio
2. **value_propositions**: Lista de 3-5 propuestas de valor principales (beneficios concretos, no features)
3. **target_audience**: A quién va dirigido el servicio (tipo de persona/negocio ideal)
4. **tone_style**: Tono y estilo de comunicación que usa el cliente (formal, casual, técnico, etc.)
5. **key_differentiators**: Qué hace diferente a este negocio vs la competencia (2-3 puntos)
6. **social_proof**: Cualquier prueba social mencionada (testimonios, números, resultados, clientes)
7. **call_to_action_hints**: Qué acción quiere que tome el prospecto (agendar llamada, visitar web, etc.)
8. **pain_points_addressed**: Problemas que resuelve el servicio (2-4 puntos)
9. **language**: Idioma principal del contenido (es/en/pt)
10. **content_type_detected**: Tipo de contenido analizado (video/image/webpage/text)

Responde SOLO en JSON válido, sin markdown ni backticks:
{
  "business_summary": "...",
  "value_propositions": ["...", "..."],
  "target_audience": "...",
  "tone_style": "...",
  "key_differentiators": ["...", "..."],
  "social_proof": ["...", "..."],
  "call_to_action_hints": "...",
  "pain_points_addressed": ["...", "..."],
  "language": "es",
  "content_type_detected": "video"
}"""

# Prompt for analyzing a lead's content (posts, reels)
LEAD_CONTENT_ANALYSIS_PROMPT = """Analiza el contenido de Instagram de este lead para personalizar un DM.

Username: {username}
Nombre: {full_name}
Bio: {bio}

Contenido de sus posts/reels recientes:
{posts_content}

Extrae información útil para escribir un DM personalizado:

1. **interests**: Temas principales que le interesan (3-5)
2. **content_style**: Estilo de su contenido (educativo, lifestyle, ventas, personal, etc.)
3. **recent_achievements**: Logros o hitos recientes mencionados
4. **engagement_topics**: Temas que generan más engagement
5. **potential_needs**: Necesidades potenciales basadas en su contenido
6. **personalization_hooks**: 2-3 datos específicos que se pueden usar para abrir conversación
7. **best_approach**: Mejor ángulo para acercarse a esta persona

Responde SOLO en JSON válido, sin markdown ni backticks:
{
  "interests": ["...", "..."],
  "content_style": "...",
  "recent_achievements": ["...", "..."],
  "engagement_topics": ["...", "..."],
  "potential_needs": ["...", "..."],
  "personalization_hooks": ["...", "..."],
  "best_approach": "..."
}"""


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from API response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


class ContentAnalysisService:
    def __init__(self):
        self.google_api_key = settings.GOOGLE_API_KEY

    @property
    def _has_api_key(self) -> bool:
        return bool(self.google_api_key) and len(self.google_api_key.strip()) >= 20

    async def analyze_content(
        self,
        content_urls: list[str] | None = None,
        content_text: str | None = None,
    ) -> dict:
        """
        Analyze client content using Gemini multimodal API.

        Supports:
        - Video URLs (YouTube, Instagram Reels, direct video links)
        - Image URLs
        - Webpage URLs (fetches and analyzes text content)
        - Raw text description

        Returns structured analysis dict.
        """
        if not self._has_api_key:
            logger.warning("No Google API key configured — cannot analyze content")
            return {"error": "No Google API key configured"}

        parts = []

        # Add text instruction
        parts.append({"text": CLIENT_CONTENT_ANALYSIS_PROMPT})

        # Process each URL
        if content_urls:
            for url in content_urls:
                url = url.strip()
                if not url:
                    continue

                content_type = self._detect_content_type(url)

                if content_type == "video":
                    # Gemini can process video URLs directly via fileData
                    # For YouTube/IG, we pass as text context with the URL
                    parts.append({
                        "text": f"\n\n[VIDEO URL para analizar]: {url}\n"
                        f"Analiza este video en detalle — su mensaje, tono, propuesta de valor, "
                        f"y cualquier información visual relevante."
                    })
                    # Try to include as file_data for direct video processing
                    if self._is_direct_video_url(url):
                        parts.append({
                            "fileData": {
                                "mimeType": "video/mp4",
                                "fileUri": url
                            }
                        })

                elif content_type == "image":
                    # Fetch image and include as inline data
                    image_data = await self._fetch_image_as_base64(url)
                    if image_data:
                        parts.append({
                            "inlineData": {
                                "mimeType": image_data["mime_type"],
                                "data": image_data["data"]
                            }
                        })
                    else:
                        parts.append({
                            "text": f"\n\n[IMAGEN URL]: {url}\nAnaliza esta imagen."
                        })

                elif content_type == "webpage":
                    # Fetch webpage text content
                    page_text = await self._fetch_webpage_text(url)
                    if page_text:
                        parts.append({
                            "text": f"\n\n[CONTENIDO DE PÁGINA WEB - {url}]:\n{page_text[:8000]}"
                        })
                    else:
                        parts.append({
                            "text": f"\n\n[WEBPAGE URL]: {url}\nAnaliza el contenido de esta página."
                        })

        # Add raw text if provided
        if content_text:
            parts.append({
                "text": f"\n\n[DESCRIPCIÓN DEL NEGOCIO/SERVICIO]:\n{content_text}"
            })

        if len(parts) <= 1:
            return {"error": "No content provided to analyze"}

        # Call Gemini API
        try:
            result = await self._call_gemini(parts)
            analysis = json.loads(_strip_code_fences(result))
            analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            analysis["source_urls"] = content_urls or []
            if content_text:
                analysis["source_text_preview"] = content_text[:200]
            logger.info(f"Content analysis complete: {analysis.get('content_type_detected', 'unknown')}")
            return analysis
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return {"error": f"Invalid JSON response: {e}", "raw_response": result[:500]}
        except Exception as e:
            logger.error(f"Content analysis failed: {type(e).__name__}: {e}")
            return {"error": str(e)}

    async def analyze_lead_content(
        self,
        username: str,
        full_name: str,
        bio: str,
        posts_data: list[dict],
    ) -> dict | None:
        """
        Analyze a lead's Instagram posts/reels for personalization.

        posts_data should contain scraped post info with captions, types, etc.
        Returns structured lead analysis or None on failure.
        """
        if not self._has_api_key:
            return None

        if not posts_data:
            return None

        # Format posts content
        posts_text = []
        for i, post in enumerate(posts_data[:10], 1):  # Max 10 posts
            caption = post.get("caption", post.get("text", ""))
            post_type = post.get("type", "post")
            likes = post.get("likesCount", post.get("likes", "?"))
            comments = post.get("commentsCount", post.get("comments", "?"))
            posts_text.append(
                f"Post {i} ({post_type}): {caption[:300]}\n"
                f"  Likes: {likes}, Comments: {comments}"
            )

        prompt = LEAD_CONTENT_ANALYSIS_PROMPT.format(
            username=username,
            full_name=full_name or "",
            bio=bio or "",
            posts_content="\n\n".join(posts_text),
        )

        try:
            parts = [{"text": prompt}]

            # Include post images if available (max 3 to avoid token limits)
            image_count = 0
            for post in posts_data[:5]:
                image_url = post.get("displayUrl", post.get("imageUrl", ""))
                if image_url and image_count < 3:
                    image_data = await self._fetch_image_as_base64(image_url)
                    if image_data:
                        parts.append({
                            "inlineData": {
                                "mimeType": image_data["mime_type"],
                                "data": image_data["data"]
                            }
                        })
                        image_count += 1

            result = await self._call_gemini(parts, max_tokens=1000)
            analysis = json.loads(_strip_code_fences(result))
            logger.info(f"Lead content analysis complete for @{username}")
            return analysis
        except Exception as e:
            logger.error(f"Lead content analysis failed for @{username}: {type(e).__name__}: {e}")
            return None

    async def analyze_campaign_content(
        self,
        campaign_id: str,
        db: AsyncSession,
        content_urls: list[str] | None = None,
        content_text: str | None = None,
    ) -> dict:
        """
        Analyze content and save results to the campaign.

        Content URLs and text can come from:
        - Direct API call (user provides URLs)
        - Campaign settings (stored content_urls field)
        """
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return {"error": "Campaign not found"}

        # Use provided URLs or fall back to campaign settings
        urls = content_urls or (campaign.settings or {}).get("content_urls", [])
        text = content_text or (campaign.settings or {}).get("content_text", "")

        if not urls and not text:
            return {"error": "No content URLs or text provided"}

        analysis = await self.analyze_content(
            content_urls=urls,
            content_text=text,
        )

        if "error" not in analysis:
            # Save analysis to campaign settings
            campaign_settings = dict(campaign.settings or {})
            campaign_settings["content_analysis"] = analysis
            if urls:
                campaign_settings["content_urls"] = urls
            if text:
                campaign_settings["content_text"] = text
            campaign.settings = campaign_settings
            await db.flush()
            logger.info(f"Content analysis saved to campaign {campaign_id}")

        return analysis

    # === Gemini API ===

    async def _call_gemini(self, parts: list[dict], max_tokens: int = 2000) -> str:
        """Call Gemini API with multimodal parts."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={self.google_api_key}"
        )

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {
                        "temperature": 0.4,
                        "maxOutputTokens": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    # === Helpers ===

    def _detect_content_type(self, url: str) -> str:
        """Detect content type from URL."""
        url_lower = url.lower()

        # Video platforms
        video_indicators = [
            "youtube.com", "youtu.be", "vimeo.com",
            "instagram.com/reel", "instagram.com/p/",
            "tiktok.com", "loom.com",
            ".mp4", ".mov", ".avi", ".webm",
        ]
        if any(ind in url_lower for ind in video_indicators):
            return "video"

        # Images
        image_indicators = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"]
        if any(ind in url_lower for ind in image_indicators):
            return "image"

        # Default to webpage
        return "webpage"

    def _is_direct_video_url(self, url: str) -> bool:
        """Check if URL points directly to a video file (not a platform page)."""
        return any(
            url.lower().endswith(ext)
            for ext in [".mp4", ".mov", ".avi", ".webm"]
        )

    async def _fetch_image_as_base64(self, url: str) -> dict | None:
        """Fetch image from URL and return as base64 data."""
        import base64

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "image/jpeg")
                if ";" in content_type:
                    content_type = content_type.split(";")[0].strip()

                data = base64.b64encode(response.content).decode("utf-8")
                return {"mime_type": content_type, "data": data}
        except Exception as e:
            logger.warning(f"Could not fetch image {url}: {e}")
            return None

    async def _fetch_webpage_text(self, url: str) -> str | None:
        """Fetch webpage and extract text content."""
        try:
            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; IGDMEngine/1.0)"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                html = response.text

                # Simple HTML to text extraction (no heavy deps)
                import re
                # Remove script and style tags
                html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
                html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
                # Remove HTML tags
                text = re.sub(r'<[^>]+>', ' ', html)
                # Clean whitespace
                text = re.sub(r'\s+', ' ', text).strip()

                return text[:8000] if text else None
        except Exception as e:
            logger.warning(f"Could not fetch webpage {url}: {e}")
            return None


content_analysis_service = ContentAnalysisService()
