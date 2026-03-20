import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.webhook import WebhookCreate, WebhookRead, WebhookUpdate
from app.services.webhook_service import webhook_service

router = APIRouter()


@router.post("/", response_model=WebhookRead, status_code=201)
async def create_webhook(
    data: WebhookCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new webhook for a client."""
    try:
        webhook = await webhook_service.create_webhook(
            client_id=str(data.client_id), data=data, db=db
        )
        return WebhookRead.from_orm_model(webhook)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=list[WebhookRead])
async def list_webhooks(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all webhooks for a client."""
    webhooks = await webhook_service.list_webhooks(
        client_id=str(client_id), db=db
    )
    return [WebhookRead.from_orm_model(w) for w in webhooks]


@router.put("/{webhook_id}", response_model=WebhookRead)
async def update_webhook(
    webhook_id: uuid.UUID,
    data: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a webhook."""
    try:
        webhook = await webhook_service.update_webhook(
            webhook_id=str(webhook_id), data=data, db=db
        )
        return WebhookRead.from_orm_model(webhook)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a webhook."""
    try:
        await webhook_service.delete_webhook(webhook_id=str(webhook_id), db=db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Send a test event to verify the webhook works."""
    try:
        result = await webhook_service.test_webhook(
            webhook_id=str(webhook_id), db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
