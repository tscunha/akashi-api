"""
AKASHI MAM API - Celery Application
"""

from celery import Celery

from app.core.config import settings


# Create Celery app
celery_app = Celery(
    "akashi_workers",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.metadata",
        "app.workers.tasks.proxy",
        "app.workers.tasks.thumbnail",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task routing
    task_routes={
        "app.workers.tasks.metadata.*": {"queue": "metadata"},
        "app.workers.tasks.proxy.*": {"queue": "proxy"},
        "app.workers.tasks.thumbnail.*": {"queue": "thumbnail"},
    },

    # Default queue
    task_default_queue="default",

    # Result expiration (24 hours)
    result_expires=86400,

    # Task acknowledgement
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Prefetch settings
    worker_prefetch_multiplier=1,

    # Retry settings
    task_annotations={
        "*": {
            "max_retries": 3,
            "default_retry_delay": 60,
        }
    },
)


# Optional: Configure periodic tasks (celery beat)
celery_app.conf.beat_schedule = {
    # Example: Check for stuck jobs every 5 minutes
    # "check-stuck-jobs": {
    #     "task": "app.workers.tasks.maintenance.check_stuck_jobs",
    #     "schedule": 300.0,
    # },
}


if __name__ == "__main__":
    celery_app.start()
