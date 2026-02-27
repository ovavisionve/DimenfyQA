from fastapi import APIRouter

from app.api.endpoints import campaigns, leads, messages, scraping, export

api_router = APIRouter()

api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(scraping.router, prefix="/scraping", tags=["scraping"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
