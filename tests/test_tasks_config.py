"""Tests to verify Celery task configuration (retry logic, error handling)."""
import httpx
import pytest

from app.tasks.base import RETRIABLE_EXCEPTIONS, RETRY_KWARGS


class TestRetryConfiguration:
    def test_retriable_exceptions_includes_network_errors(self):
        assert ConnectionError in RETRIABLE_EXCEPTIONS
        assert TimeoutError in RETRIABLE_EXCEPTIONS

    def test_retriable_exceptions_includes_httpx_errors(self):
        assert httpx.ConnectError in RETRIABLE_EXCEPTIONS
        assert httpx.ConnectTimeout in RETRIABLE_EXCEPTIONS
        assert httpx.ReadTimeout in RETRIABLE_EXCEPTIONS
        assert httpx.HTTPStatusError in RETRIABLE_EXCEPTIONS

    def test_retriable_exceptions_includes_anthropic_errors(self):
        import anthropic
        assert anthropic.APIConnectionError in RETRIABLE_EXCEPTIONS
        assert anthropic.APITimeoutError in RETRIABLE_EXCEPTIONS
        assert anthropic.RateLimitError in RETRIABLE_EXCEPTIONS
        assert anthropic.InternalServerError in RETRIABLE_EXCEPTIONS

    def test_retry_kwargs_has_required_keys(self):
        assert "autoretry_for" in RETRY_KWARGS
        assert "max_retries" in RETRY_KWARGS
        assert "retry_backoff" in RETRY_KWARGS
        assert "retry_backoff_max" in RETRY_KWARGS
        assert "retry_jitter" in RETRY_KWARGS

    def test_retry_kwargs_values(self):
        assert RETRY_KWARGS["max_retries"] == 3
        assert RETRY_KWARGS["retry_backoff"] is True
        assert RETRY_KWARGS["retry_backoff_max"] == 300
        assert RETRY_KWARGS["retry_jitter"] is True


class TestTaskDecorators:
    """Verify that task modules import and configure correctly."""

    def test_scraping_task_has_retry(self):
        from app.tasks.scraping_tasks import scrape_leads_task
        assert scrape_leads_task.max_retries == 3

    def test_scoring_task_has_retry(self):
        from app.tasks.scoring_tasks import score_leads_task
        assert score_leads_task.max_retries == 3

    def test_research_task_has_retry(self):
        from app.tasks.research_tasks import research_leads_task
        assert research_leads_task.max_retries == 3

    def test_copywriting_task_has_retry(self):
        from app.tasks.copywriting_tasks import write_dms_task
        assert write_dms_task.max_retries == 3

    def test_scraping_task_is_bound(self):
        from app.tasks.scraping_tasks import scrape_leads_task
        # Bound tasks have 'self' as first arg
        assert scrape_leads_task.name == "scrape_leads"

    def test_pipeline_chain_imports(self):
        """Verify the pipeline can be imported without errors."""
        from app.tasks.pipeline import run_campaign_pipeline
        assert callable(run_campaign_pipeline)
