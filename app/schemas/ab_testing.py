import uuid
from typing import Optional

from pydantic import BaseModel


class VariantStats(BaseModel):
    sent: int = 0
    replied: int = 0
    reply_rate: float = 0.0
    positive_replies: int = 0
    conversion_rate: float = 0.0


class ABTestResults(BaseModel):
    campaign_id: uuid.UUID
    variant_a: VariantStats
    variant_b: VariantStats
    winner: Optional[str] = None
    confidence: str = "low"
    total_sent: int = 0
    recommendation: str = ""
