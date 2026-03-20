from fastapi import APIRouter, Depends

from app.api.auth import verify_api_key
from app.api.endpoints import campaigns, clients, follow_ups, leads, messages, scraping, export

api_router = APIRouter(dependencies=[Depends(verify_api_key)])

api_router.include_router(clients.router, prefix="/clients", tags=["clients"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(scraping.router, prefix="/scraping", tags=["scraping"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(follow_ups.router, prefix="/follow-ups", tags=["follow-ups"])
