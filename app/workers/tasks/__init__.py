"""
AKASHI MAM API - Worker Tasks
"""

from app.workers.tasks.metadata import extract_metadata
from app.workers.tasks.proxy import generate_proxy
from app.workers.tasks.thumbnail import generate_thumbnail
from app.workers.tasks.ingest import process_ingest, run_ingest_pipeline, finalize_ingest
from app.workers.tasks.maintenance import (
    cleanup_old_jobs,
    cleanup_orphan_storage,
    check_stuck_jobs,
    health_check,
    calculate_storage_stats,
)

__all__ = [
    # Media tasks
    "extract_metadata",
    "generate_proxy",
    "generate_thumbnail",
    # Ingest tasks
    "process_ingest",
    "run_ingest_pipeline",
    "finalize_ingest",
    # Maintenance tasks
    "cleanup_old_jobs",
    "cleanup_orphan_storage",
    "check_stuck_jobs",
    "health_check",
    "calculate_storage_stats",
]
