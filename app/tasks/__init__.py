# Import all task modules so Celery registers them
from app.tasks.scraping_tasks import scrape_leads_task  # noqa: F401
from app.tasks.scoring_tasks import score_leads_task  # noqa: F401
from app.tasks.research_tasks import research_leads_task  # noqa: F401
from app.tasks.copywriting_tasks import write_dms_task  # noqa: F401
