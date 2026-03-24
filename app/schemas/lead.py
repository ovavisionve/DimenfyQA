import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LeadRead(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    client_id: uuid.UUID
    ig_username: str
    ig_full_name: Optional[str]
    ig_bio: Optional[str]
    ig_bio_clean: Optional[str]
    ig_website: Optional[str]
    ig_category: Optional[str]
    ig_follower_count: Optional[int]
    ig_following_count: Optional[int]
    ig_is_private: Optional[bool]
    ig_posts: Optional[list] = None
    ig_post_analysis: Optional[dict] = None
    score: Optional[int]
    score_reason: Optional[str]
    lead_category: Optional[str]
    research_summary: Optional[str]
    dm_message: Optional[str]
    dm_variant_b: Optional[str] = None
    status: str
    is_duplicate: bool
    send_attempts: int = 0
    send_error: Optional[str] = None
    delivery_status: Optional[str] = None
    dm_variant_used: Optional[str] = None
    replied_at: Optional[datetime] = None
    reply_text: Optional[str] = None
    reply_classification: Optional[str] = None
    conversation_status: str = "pending"
    follow_up_count: int = 0
    last_follow_up_at: Optional[datetime] = None
    next_follow_up_at: Optional[datetime] = None
    scraped_at: Optional[datetime]
    sent_at: Optional[datetime] = None
    scored_at: Optional[datetime]
    researched_at: Optional[datetime]
    dm_generated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadScored(BaseModel):
    id: uuid.UUID
    ig_username: str
    ig_full_name: Optional[str]
    ig_bio_clean: Optional[str]
    score: Optional[int]
    score_reason: Optional[str]
    lead_category: Optional[str]
    status: str

    model_config = {"from_attributes": True}


class LeadDMReady(BaseModel):
    id: uuid.UUID
    ig_username: str
    ig_full_name: Optional[str]
    score: Optional[int]
    lead_category: Optional[str]
    dm_message: Optional[str]
    dm_variant_b: Optional[str]
    status: str

    model_config = {"from_attributes": True}
