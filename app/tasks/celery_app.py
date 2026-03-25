from celery import Celery

from app.config import settings

celery_app = Celery("ig_dm_engine")

celery_app.config_from_object({
    "broker_url": settings.REDIS_URL,
    "result_backend": settings.REDIS_URL,
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "task_track_started": True,
    "task_acks_late": True,
    "worker_prefetch_multiplier": 1,
})

# Auto-discover tasks in the tasks package
celery_app.autodiscover_tasks([
    "app.tasks.scraping_tasks",
    "app.tasks.scoring_tasks",
    "app.tasks.research_tasks",
    "app.tasks.copywriting_tasks",
    "app.tasks.sending_tasks",
    "app.tasks.comment_tasks",
])
