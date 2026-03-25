from fastapi import APIRouter, Depends

from app.api.auth import verify_api_key
from app.api.endpoints import auth, campaigns, clients, content_analysis, crm, follow_ups, leads, messages, scraping, export, unibox, webhooks

api_router = APIRouter(dependencies=[Depends(verify_api_key)])

# Auth routes — NO API key required (they issue their own tokens)
auth_router = APIRouter()
auth_router.include_router(auth.router, prefix="/auth", tags=["auth"])

api_router.include_router(clients.router, prefix="/clients", tags=["clients"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(scraping.router, prefix="/scraping", tags=["scraping"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(follow_ups.router, prefix="/follow-ups", tags=["follow-ups"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(content_analysis.router, prefix="/content", tags=["content-analysis"])
api_router.include_router(unibox.router, prefix="/unibox", tags=["unibox"])
api_router.include_router(crm.router, prefix="/crm", tags=["crm"])
