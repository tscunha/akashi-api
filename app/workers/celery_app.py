"""
AKASHI MAM API - Celery Application Configuration
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
        "app.workers.tasks.ingest",
        "app.workers.tasks.maintenance",
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

    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 min soft limit

    # Worker settings
    worker_prefetch_multiplier=1,  # Fair task distribution
    worker_max_tasks_per_child=100,  # Restart after 100 tasks
    worker_disable_rate_limits=False,

    # Result backend settings
    result_expires=86400,  # 24 hours
    result_extended=True,

    # Task routing
    task_routes={
        "app.workers.tasks.metadata.*": {"queue": "metadata"},
        "app.workers.tasks.proxy.*": {"queue": "media"},
        "app.workers.tasks.thumbnail.*": {"queue": "media"},
        "app.workers.tasks.ingest.*": {"queue": "ingest"},
        "app.workers.tasks.maintenance.*": {"queue": "maintenance"},
    },

    # Default queue
    task_default_queue="default",

    # Retry settings
    task_annotations={
        "*": {
            "max_retries": 3,
            "default_retry_delay": 60,
        },
        # High priority tasks
        "app.workers.tasks.maintenance.health_check": {
            "rate_limit": "1/m",  # Max 1 per minute
        },
    },
)


# Periodic tasks (celery beat)
celery_app.conf.beat_schedule = {
    # Cleanup old completed/failed jobs every hour
    "cleanup-old-jobs": {
        "task": "app.workers.tasks.maintenance.cleanup_old_jobs",
        "schedule": 3600.0,  # Every hour
        "kwargs": {"days": 30},
    },
    # Check for stuck jobs every 5 minutes
    "check-stuck-jobs": {
        "task": "app.workers.tasks.maintenance.check_stuck_jobs",
        "schedule": 300.0,  # Every 5 minutes
        "kwargs": {"timeout_minutes": 60},
    },
    # Health check every minute
    "health-check": {
        "task": "app.workers.tasks.maintenance.health_check",
        "schedule": 60.0,  # Every minute
    },
    # Calculate storage stats every 6 hours
    "storage-stats": {
        "task": "app.workers.tasks.maintenance.calculate_storage_stats",
        "schedule": 21600.0,  # Every 6 hours
    },
}


# Task priority levels (lower = higher priority)
class TaskPriority:
    """Task priority levels."""

    CRITICAL = 0
    HIGH = 3
    NORMAL = 5
    LOW = 7
    BACKGROUND = 9


if __name__ == "__main__":
    celery_app.start()
