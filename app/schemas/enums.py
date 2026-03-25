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


class ConversationStatus(StrEnum):
    PENDING = "pending"
    AWAITING_REPLY = "awaiting_reply"
    REPLIED = "replied"
    ENGAGED = "engaged"
    CLOSED = "closed"


class ReplyClassification(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    QUESTION = "question"
    NOT_INTERESTED = "not_interested"
    OUT_OF_OFFICE = "out_of_office"
    SPAM = "spam"


class CrmStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    REPLIED = "replied"
    INTERESTED = "interested"
    CALL_SCHEDULED = "call_scheduled"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
