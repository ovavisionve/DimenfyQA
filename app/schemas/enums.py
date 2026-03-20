from enum import StrEnum


class CampaignStatus(StrEnum):
    PENDING = "pending"
    SCRAPING = "scraping"
    SCORING = "scoring"
    RESEARCHING = "researching"
    WRITING = "writing"
    READY = "ready"
    SENDING = "sending"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"


class LeadStatus(StrEnum):
    SCRAPED = "scraped"
    SCORED = "scored"
    RESEARCHED = "researched"
    DM_READY = "dm_ready"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRY = "retry"


class SourceType(StrEnum):
    FOLLOWERS = "followers"
    COMMENTS = "comments"
    PROFILES = "profiles"


class LeadCategory(StrEnum):
    COACH = "coach"
    ECOMMERCE = "ecommerce"
    SAAS = "saas"
    AGENCY = "agency"
    CREATOR = "creator"
    LOCAL_BUSINESS = "local_business"
    OTHER = "other"
