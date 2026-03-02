import pytest
from pydantic import ValidationError

from app.schemas.enums import CampaignStatus, LeadStatus, SourceType, LeadCategory
from app.schemas.campaign import CampaignCreate


class TestEnums:
    def test_campaign_status_values(self):
        assert CampaignStatus.PENDING == "pending"
        assert CampaignStatus.SCRAPING == "scraping"
        assert CampaignStatus.SCORING == "scoring"
        assert CampaignStatus.READY == "ready"
        assert CampaignStatus.FAILED == "failed"

    def test_lead_status_values(self):
        assert LeadStatus.SCRAPED == "scraped"
        assert LeadStatus.SCORED == "scored"
        assert LeadStatus.RESEARCHED == "researched"
        assert LeadStatus.DM_READY == "dm_ready"

    def test_source_type_values(self):
        assert SourceType.FOLLOWERS == "followers"
        assert SourceType.COMMENTS == "comments"
        assert SourceType.PROFILES == "profiles"

    def test_lead_category_values(self):
        assert LeadCategory.COACH == "coach"
        assert LeadCategory.ECOMMERCE == "ecommerce"
        assert LeadCategory.OTHER == "other"


class TestSchemaValidation:
    def test_campaign_create_valid_source_type(self):
        import uuid
        data = CampaignCreate(
            client_id=uuid.uuid4(),
            name="Test Campaign",
            source_type="followers",
            source_value="@testuser",
        )
        assert data.source_type == SourceType.FOLLOWERS

    def test_campaign_create_invalid_source_type(self):
        import uuid
        with pytest.raises(ValidationError) as exc_info:
            CampaignCreate(
                client_id=uuid.uuid4(),
                name="Test Campaign",
                source_type="invalid_type",
                source_value="@testuser",
            )
        assert "source_type" in str(exc_info.value)
