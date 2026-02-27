import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageRead(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    campaign_id: uuid.UUID
    client_id: uuid.UUID
    content: str
    variant: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
