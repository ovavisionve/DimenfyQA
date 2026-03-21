from fastapi import APIRouter, Depends

from app.api.auth import verify_api_key
from app.api.endpoints import campaigns, clients, content_analysis, follow_ups, leads, messages, scraping, export, webhooks

api_router = APIRouter(dependencies=[Depends(verify_api_key)])

api_router.include_router(clients.router, prefix="/clients", tags=["clients"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(scraping.router, prefix="/scraping", tags=["scraping"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(follow_ups.router, prefix="/follow-ups", tags=["follow-ups"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(content_analysis.router, prefix="/content", tags=["content-analysis"])
