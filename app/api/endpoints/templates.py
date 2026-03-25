from fastapi import APIRouter, HTTPException

router = APIRouter()

TEMPLATES = [
    {
        "id": "agency_outreach",
        "name": "Agencias de Marketing",
        "description": "Target marketing agencies. Ideal for B2B services selling to digital agencies.",
        "source_type": "comments",
        "suggested_source_value": "https://www.instagram.com/p/XXXXX — post from a popular marketing account",
        "settings": {
            "bio_keywords": [
                "agencia",
                "agency",
                "marketing digital",
                "social media",
                "publicidad",
            ],
            "sending_hours_start": "09:00",
            "sending_hours_end": "18:00",
            "sending_timezone": "America/Bogota",
            "max_leads": 100,
        },
    },
    {
        "id": "coach_outreach",
        "name": "Coaches y Consultores",
        "description": "Target coaches and consultants. Great for high-ticket offers and mentorship programs.",
        "source_type": "comments",
        "suggested_source_value": "https://www.instagram.com/p/XXXXX — post from a coaching or personal development account",
        "settings": {
            "bio_keywords": [
                "coach",
                "consultor",
                "mentor",
                "coaching",
                "emprendedor",
            ],
            "sending_hours_start": "08:00",
            "sending_hours_end": "20:00",
            "sending_timezone": "America/Mexico_City",
            "max_leads": 100,
        },
    },
    {
        "id": "ecommerce_outreach",
        "name": "E-Commerce / Tiendas Online",
        "description": "Target online stores and e-commerce businesses. Perfect for tools, logistics, or marketing services.",
        "source_type": "comments",
        "suggested_source_value": "https://www.instagram.com/p/XXXXX — post from a popular e-commerce or dropshipping account",
        "settings": {
            "bio_keywords": [
                "tienda",
                "shop",
                "ecommerce",
                "envíos",
                "compra",
            ],
            "sending_hours_start": "10:00",
            "sending_hours_end": "21:00",
            "sending_timezone": "America/Caracas",
            "max_leads": 100,
        },
    },
    {
        "id": "saas_outreach",
        "name": "SaaS / Software",
        "description": "Target SaaS companies and tech startups. Ideal for dev tools, integrations, or growth services.",
        "source_type": "comments",
        "suggested_source_value": "https://www.instagram.com/p/XXXXX — post from a startup or tech community account",
        "settings": {
            "bio_keywords": [
                "saas",
                "software",
                "plataforma",
                "app",
                "startup",
                "tech",
            ],
            "sending_hours_start": "09:00",
            "sending_hours_end": "19:00",
            "sending_timezone": "America/New_York",
            "max_leads": 100,
        },
    },
    {
        "id": "restaurant_outreach",
        "name": "Restaurantes y Comida",
        "description": "Target restaurants and food businesses. Great for delivery platforms, POS systems, or marketing services.",
        "source_type": "comments",
        "suggested_source_value": "https://www.instagram.com/p/XXXXX — post from a popular food or restaurant account",
        "settings": {
            "bio_keywords": [
                "restaurante",
                "chef",
                "comida",
                "food",
                "delivery",
                "cocina",
            ],
            "sending_hours_start": "10:00",
            "sending_hours_end": "22:00",
            "sending_timezone": "America/Caracas",
            "max_leads": 100,
        },
    },
    {
        "id": "fitness_outreach",
        "name": "Fitness y Bienestar",
        "description": "Target fitness professionals and wellness businesses. Perfect for supplements, apps, or coaching platforms.",
        "source_type": "comments",
        "suggested_source_value": "https://www.instagram.com/p/XXXXX — post from a popular fitness or wellness account",
        "settings": {
            "bio_keywords": [
                "fitness",
                "gym",
                "entrenador",
                "nutrición",
                "personal trainer",
                "wellness",
            ],
            "sending_hours_start": "06:00",
            "sending_hours_end": "20:00",
            "sending_timezone": "America/Lima",
            "max_leads": 100,
        },
    },
]

_TEMPLATES_BY_ID = {t["id"]: t for t in TEMPLATES}


@router.get("/")
async def list_templates():
    """Return all available campaign templates."""
    return TEMPLATES


@router.get("/{template_id}")
async def get_template(template_id: str):
    """Return a single campaign template by ID."""
    template = _TEMPLATES_BY_ID.get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return template
