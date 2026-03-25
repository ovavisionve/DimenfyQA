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
    "task_reject_on_worker_lost": True,
    "worker_prefetch_multiplier": 1,
    "broker_transport_options": {
        "visibility_timeout": 43200,  # 12h — re-queue unacked tasks
    },
    # Celery Beat — periodic task schedule
    "beat_schedule": {
        "check-all-inboxes": {
            "task": "check_all_inboxes",
            "schedule": settings.INBOX_CHECK_INTERVAL,  # default 300s (5 min)
        },
        "check-all-follow-ups": {
            "task": "check_all_follow_ups",
            "schedule": settings.FOLLOWUP_CHECK_INTERVAL,  # default 3600s (1 hour)
        },
    },
})

# Auto-discover tasks in the tasks package
celery_app.autodiscover_tasks([
    "app.tasks.scraping_tasks",
    "app.tasks.scoring_tasks",
    "app.tasks.research_tasks",
    "app.tasks.copywriting_tasks",
    "app.tasks.sending_tasks",
    "app.tasks.comment_tasks",
    "app.tasks.inbox_tasks",
    "app.tasks.followup_tasks",
])
