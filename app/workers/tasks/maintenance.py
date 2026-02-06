"""
AKASHI MAM API - Maintenance Tasks
Scheduled tasks for system health and cleanup.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from celery import shared_task
from sqlalchemy import delete, func, select, update

from app.core.database import get_db_context


logger = logging.getLogger(__name__)


# =============================================================================
# Cleanup Tasks
# =============================================================================


async def _cleanup_old_jobs_async(days: int = 30) -> dict:
    """Remove completed jobs older than specified days."""
    from app.models import IngestJob

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_db_context() as db:
        # Count jobs to delete
        count_result = await db.execute(
            select(func.count()).select_from(IngestJob).where(
                IngestJob.completed_at < cutoff_date,
                IngestJob.status.in_(["completed", "failed"]),
            )
        )
        count = count_result.scalar() or 0

        if count == 0:
            return {"deleted": 0, "message": "No old jobs to clean up"}

        # Delete old jobs
        await db.execute(
            delete(IngestJob).where(
                IngestJob.completed_at < cutoff_date,
                IngestJob.status.in_(["completed", "failed"]),
            )
        )
        await db.commit()

        logger.info(f"Cleaned up {count} old jobs older than {days} days")
        return {
            "deleted": count,
            "cutoff_date": cutoff_date.isoformat(),
            "message": f"Cleaned up {count} old jobs",
        }


@shared_task(bind=True, name="app.workers.tasks.maintenance.cleanup_old_jobs")
def cleanup_old_jobs(self, days: int = 30):
    """
    Clean up completed/failed jobs older than specified days.

    Args:
        days: Number of days to keep jobs (default: 30)
    """
    return asyncio.get_event_loop().run_until_complete(
        _cleanup_old_jobs_async(days)
    )


async def _cleanup_orphan_storage_async() -> dict:
    """Find and optionally clean up storage locations without valid assets."""
    from app.models import Asset, AssetStorageLocation

    async with get_db_context() as db:
        # Find orphan storage locations
        orphan_result = await db.execute(
            select(AssetStorageLocation).where(
                ~AssetStorageLocation.asset_id.in_(
                    select(Asset.id)
                )
            )
        )
        orphans = list(orphan_result.scalars().all())

        if not orphans:
            return {"orphans_found": 0, "message": "No orphan storage locations"}

        # For now, just report - don't delete automatically
        orphan_info = [
            {
                "id": str(o.id),
                "path": o.path,
                "bucket": o.bucket,
                "size_bytes": o.file_size_bytes,
            }
            for o in orphans
        ]

        logger.warning(f"Found {len(orphans)} orphan storage locations")
        return {
            "orphans_found": len(orphans),
            "orphans": orphan_info,
            "message": "Orphan storage locations found (not deleted)",
        }


@shared_task(bind=True, name="app.workers.tasks.maintenance.cleanup_orphan_storage")
def cleanup_orphan_storage(self):
    """
    Find orphan storage locations without valid assets.
    Does not delete automatically - reports for manual review.
    """
    return asyncio.get_event_loop().run_until_complete(
        _cleanup_orphan_storage_async()
    )


# =============================================================================
# Health Check Tasks
# =============================================================================


async def _check_stuck_jobs_async(timeout_minutes: int = 60) -> dict:
    """Find and mark stuck jobs as failed."""
    from app.models import IngestJob

    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

    async with get_db_context() as db:
        # Find stuck jobs
        stuck_result = await db.execute(
            select(IngestJob).where(
                IngestJob.status == "processing",
                IngestJob.started_at < cutoff_time,
            )
        )
        stuck_jobs = list(stuck_result.scalars().all())

        if not stuck_jobs:
            return {"stuck_jobs": 0, "message": "No stuck jobs found"}

        # Mark as failed
        stuck_ids = [j.id for j in stuck_jobs]
        await db.execute(
            update(IngestJob).where(
                IngestJob.id.in_(stuck_ids)
            ).values(
                status="failed",
                error_message=f"Job timed out after {timeout_minutes} minutes",
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        logger.warning(f"Marked {len(stuck_jobs)} stuck jobs as failed")
        return {
            "stuck_jobs": len(stuck_jobs),
            "job_ids": [str(j) for j in stuck_ids],
            "message": f"Marked {len(stuck_jobs)} stuck jobs as failed",
        }


@shared_task(bind=True, name="app.workers.tasks.maintenance.check_stuck_jobs")
def check_stuck_jobs(self, timeout_minutes: int = 60):
    """
    Find jobs stuck in 'processing' state and mark as failed.

    Args:
        timeout_minutes: Consider job stuck after this many minutes
    """
    return asyncio.get_event_loop().run_until_complete(
        _check_stuck_jobs_async(timeout_minutes)
    )


async def _health_check_async() -> dict:
    """Perform a system health check."""
    from app.models import Asset, IngestJob, User
    from app.services import StorageService

    health = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "unknown",
        "storage": "unknown",
        "stats": {},
    }

    # Check database
    try:
        async with get_db_context() as db:
            # Count assets
            asset_count = await db.execute(
                select(func.count()).select_from(Asset)
            )
            health["stats"]["total_assets"] = asset_count.scalar() or 0

            # Count users
            user_count = await db.execute(
                select(func.count()).select_from(User)
            )
            health["stats"]["total_users"] = user_count.scalar() or 0

            # Count pending jobs
            pending_count = await db.execute(
                select(func.count()).select_from(IngestJob).where(
                    IngestJob.status == "pending"
                )
            )
            health["stats"]["pending_jobs"] = pending_count.scalar() or 0

            # Count processing jobs
            processing_count = await db.execute(
                select(func.count()).select_from(IngestJob).where(
                    IngestJob.status == "processing"
                )
            )
            health["stats"]["processing_jobs"] = processing_count.scalar() or 0

            health["database"] = "healthy"

    except Exception as e:
        health["database"] = f"error: {str(e)}"
        logger.error(f"Database health check failed: {e}")

    # Check storage (MinIO)
    try:
        storage = StorageService()
        # Try to list buckets (simple health check)
        buckets_ok = await storage.check_health()
        health["storage"] = "healthy" if buckets_ok else "degraded"
    except Exception as e:
        health["storage"] = f"error: {str(e)}"
        logger.error(f"Storage health check failed: {e}")

    # Overall status
    if health["database"] == "healthy" and health["storage"] == "healthy":
        health["status"] = "healthy"
    elif "error" in health["database"] or "error" in health["storage"]:
        health["status"] = "unhealthy"
    else:
        health["status"] = "degraded"

    logger.info(f"Health check: {health['status']}")
    return health


@shared_task(bind=True, name="app.workers.tasks.maintenance.health_check")
def health_check(self):
    """
    Perform a system health check.

    Checks:
    - Database connectivity and basic stats
    - Storage (MinIO) connectivity
    - Job queue status
    """
    return asyncio.get_event_loop().run_until_complete(
        _health_check_async()
    )


# =============================================================================
# Statistics Tasks
# =============================================================================


async def _calculate_storage_stats_async() -> dict:
    """Calculate storage usage statistics per tenant."""
    from app.models import AssetStorageLocation, Tenant
    from sqlalchemy import func

    async with get_db_context() as db:
        # Get storage usage per tenant
        stats_result = await db.execute(
            select(
                AssetStorageLocation.tenant_id,
                func.sum(AssetStorageLocation.file_size_bytes).label("total_bytes"),
                func.count().label("file_count"),
            ).group_by(AssetStorageLocation.tenant_id)
        )

        stats = []
        for row in stats_result.all():
            # Get tenant name
            tenant = await db.get(Tenant, row.tenant_id)
            stats.append({
                "tenant_id": str(row.tenant_id),
                "tenant_code": tenant.code if tenant else "unknown",
                "total_bytes": row.total_bytes or 0,
                "total_gb": round((row.total_bytes or 0) / (1024**3), 2),
                "file_count": row.file_count or 0,
            })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenants": stats,
            "total_bytes": sum(s["total_bytes"] for s in stats),
            "total_files": sum(s["file_count"] for s in stats),
        }


@shared_task(bind=True, name="app.workers.tasks.maintenance.calculate_storage_stats")
def calculate_storage_stats(self):
    """
    Calculate storage usage statistics.

    Reports storage usage per tenant and overall totals.
    """
    return asyncio.get_event_loop().run_until_complete(
        _calculate_storage_stats_async()
    )
