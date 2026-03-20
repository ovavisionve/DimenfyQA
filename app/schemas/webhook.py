import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class WebhookCreate(BaseModel):
    client_id: uuid.UUID
    url: str
    events: list[str]
    secret: Optional[str] = None


class WebhookRead(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    url: str
    secret: Optional[str]
    events: list[str]
    is_active: bool
    last_triggered_at: Optional[datetime]
    last_status_code: Optional[int]
    failure_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, webhook) -> "WebhookRead":
        """Convert ORM model to schema, splitting comma-separated events into list."""
        return cls(
            id=webhook.id,
            client_id=webhook.client_id,
            url=webhook.url,
            secret=webhook.secret,
            events=webhook.events.split(",") if webhook.events else [],
            is_active=webhook.is_active,
            last_triggered_at=webhook.last_triggered_at,
            last_status_code=webhook.last_status_code,
            failure_count=webhook.failure_count,
            created_at=webhook.created_at,
            updated_at=webhook.updated_at,
        )


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[list[str]] = None
    is_active: Optional[bool] = None


class WebhookEvent(BaseModel):
    event_type: str
    timestamp: datetime
    payload: dict[str, Any]
