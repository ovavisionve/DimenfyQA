import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.enums import CampaignStatus, SourceType


class CampaignCreate(BaseModel):
    client_id: uuid.UUID
    name: str
    source_type: SourceType
    source_value: str
    settings: dict = {}


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[CampaignStatus] = None
    settings: Optional[dict] = None


class CampaignRead(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    source_type: str
    source_value: str
    status: str
    settings: dict
    stats: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignStats(BaseModel):
    campaign_id: uuid.UUID
    total_leads: int = 0
    scored_leads: int = 0
    researched_leads: int = 0
    dm_ready_leads: int = 0
    sent_leads: int = 0
    failed_leads: int = 0
    avg_score: Optional[float] = None
    status: str
