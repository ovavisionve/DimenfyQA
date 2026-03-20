import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FollowUpRuleCreate(BaseModel):
    campaign_id: uuid.UUID
    step_number: int
    delay_days: int
    template_prompt: Optional[str] = None
    max_attempts: int = 3


class FollowUpRuleRead(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    client_id: uuid.UUID
    step_number: int
    delay_days: int
    template_prompt: Optional[str]
    max_attempts: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FollowUpRuleUpdate(BaseModel):
    delay_days: Optional[int] = None
    template_prompt: Optional[str] = None
    is_active: Optional[bool] = None
