from typing import Optional

from pydantic import BaseModel


class FunnelStage(BaseModel):
    name: str
    count: int
    percentage: float


class ScoreDistribution(BaseModel):
    range_label: str
    count: int


class CategoryBreakdown(BaseModel):
    category: str
    count: int
    percentage: float


class TimelinePoint(BaseModel):
    date: str
    sent_count: int
    replied_count: int


class ConversionStep(BaseModel):
    stage: str
    count: int
    conversion_pct: float


class CampaignAnalytics(BaseModel):
    campaign_id: str
    funnel: list[FunnelStage]
    response_rate: float
    score_distribution: list[ScoreDistribution]
    category_breakdown: list[CategoryBreakdown]
    timeline: list[TimelinePoint]
    avg_score: float
    conversion_funnel: list[ConversionStep]
    total_leads: int
    total_sent: int
    total_replied: int


class ClientAnalytics(BaseModel):
    client_id: str
    total_campaigns: int
    total_leads: int
    total_sent: int
    total_replied: int
    avg_score: float
    response_rate: float
    total_scored: int
    total_dm_ready: int
    category_breakdown: list[CategoryBreakdown]


class TopCampaign(BaseModel):
    campaign_id: str
    name: str
    status: str
    total_leads: int
    sent: int
    replied: int
    response_rate: float
    avg_score: float
