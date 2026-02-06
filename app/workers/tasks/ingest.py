"""
AKASHI MAM API - Ingest Pipeline Worker
Orchestrates the complete ingest workflow.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import chain, chord, group, shared_task

from app.core.database import get_db_context
from app.models import Asset, IngestJob


logger = logging.getLogger(__name__)


async def _process_ingest_async(asset_id: str, input_path: str) -> dict:
    """
    Process a complete ingest for an asset.
    Creates jobs for metadata, proxy, and thumbnail.
    """
    from app.workers.tasks.metadata import extract_metadata
    from app.workers.tasks.proxy import generate_proxy
    from app.workers.tasks.thumbnail import generate_thumbnail

    async with get_db_context() as db:
        asset = await db.get(Asset, UUID(asset_id))
        if not asset:
            return {"error": "Asset not found"}

        tenant_id = str(asset.tenant_id)

        # Create metadata job
        metadata_job = IngestJob(
            tenant_id=asset.tenant_id,
            asset_id=asset.id,
            job_type="metadata",
            input_path=input_path,
            status="pending",
            priority=10,
        )
        db.add(metadata_job)

        # Create proxy job
        proxy_job = IngestJob(
            tenant_id=asset.tenant_id,
            asset_id=asset.id,
            job_type="proxy",
            input_path=input_path,
            status="pending",
            priority=20,
        )
        db.add(proxy_job)

        # Create thumbnail job
        thumbnail_job = IngestJob(
            tenant_id=asset.tenant_id,
            asset_id=asset.id,
            job_type="thumbnail",
            input_path=input_path,
            status="pending",
            priority=30,
        )
        db.add(thumbnail_job)

        await db.flush()

        job_ids = {
            "metadata": str(metadata_job.id),
            "proxy": str(proxy_job.id),
            "thumbnail": str(thumbnail_job.id),
        }

        await db.commit()

        logger.info(f"Created ingest jobs for asset {asset_id}: {job_ids}")

        return {
            "asset_id": asset_id,
            "jobs": job_ids,
            "status": "queued",
        }


@shared_task(bind=True, name="app.workers.tasks.ingest.process_ingest")
def process_ingest(self, asset_id: str, input_path: str):
    """
    Start the ingest pipeline for an asset.

    This creates jobs for:
    - Metadata extraction (FFprobe)
    - Proxy generation (H.264 720p)
    - Thumbnail generation (JPEG)

    Args:
        asset_id: The Asset ID
        input_path: Path to the original file in storage
    """
    return asyncio.get_event_loop().run_until_complete(
        _process_ingest_async(asset_id, input_path)
    )


async def _run_ingest_pipeline_async(asset_id: str, input_path: str) -> dict:
    """
    Run the complete ingest pipeline with job tracking.
    """
    from app.workers.tasks.metadata import extract_metadata
    from app.workers.tasks.proxy import generate_proxy
    from app.workers.tasks.thumbnail import generate_thumbnail

    async with get_db_context() as db:
        asset = await db.get(Asset, UUID(asset_id))
        if not asset:
            return {"error": "Asset not found"}

        # Create master job for tracking
        master_job = IngestJob(
            tenant_id=asset.tenant_id,
            asset_id=asset.id,
            job_type="ingest_pipeline",
            input_path=input_path,
            status="processing",
            started_at=datetime.now(timezone.utc),
            priority=0,
        )
        db.add(master_job)
        await db.flush()
        await db.commit()

        master_job_id = str(master_job.id)

    # Run jobs in parallel using Celery group
    # Metadata first, then proxy and thumbnail in parallel
    try:
        # Create the jobs first
        result = await _process_ingest_async(asset_id, input_path)

        if "error" in result:
            return result

        job_ids = result["jobs"]

        # Launch tasks
        # Metadata must complete first (needed for proxy/thumbnail timing)
        metadata_result = extract_metadata.delay(
            job_ids["metadata"], asset_id, input_path
        )

        # Wait for metadata, then run proxy and thumbnail in parallel
        # For now, just queue them all
        proxy_result = generate_proxy.delay(
            job_ids["proxy"], asset_id, input_path
        )
        thumbnail_result = generate_thumbnail.delay(
            job_ids["thumbnail"], asset_id, input_path
        )

        # Update master job
        async with get_db_context() as db:
            master_job = await db.get(IngestJob, UUID(master_job_id))
            if master_job:
                master_job.result = {
                    "child_jobs": job_ids,
                    "task_ids": {
                        "metadata": metadata_result.id,
                        "proxy": proxy_result.id,
                        "thumbnail": thumbnail_result.id,
                    },
                }
                await db.commit()

        return {
            "master_job_id": master_job_id,
            "child_jobs": job_ids,
            "status": "processing",
        }

    except Exception as e:
        logger.error(f"Ingest pipeline failed for asset {asset_id}: {e}")
        async with get_db_context() as db:
            master_job = await db.get(IngestJob, UUID(master_job_id))
            if master_job:
                master_job.status = "failed"
                master_job.error_message = str(e)
                master_job.completed_at = datetime.now(timezone.utc)
                await db.commit()
        return {"error": str(e)}


@shared_task(bind=True, name="app.workers.tasks.ingest.run_ingest_pipeline")
def run_ingest_pipeline(self, asset_id: str, input_path: str):
    """
    Run the complete ingest pipeline.

    This orchestrates:
    1. Create tracking jobs
    2. Run metadata extraction
    3. Run proxy and thumbnail generation in parallel
    4. Update asset status on completion

    Args:
        asset_id: The Asset ID
        input_path: Path to the original file in storage
    """
    return asyncio.get_event_loop().run_until_complete(
        _run_ingest_pipeline_async(asset_id, input_path)
    )


async def _finalize_ingest_async(asset_id: str) -> dict:
    """Mark an asset as available after all jobs complete."""
    async with get_db_context() as db:
        asset = await db.get(Asset, UUID(asset_id))
        if not asset:
            return {"error": "Asset not found"}

        # Check if all jobs completed
        from sqlalchemy import select, func
        from app.models import IngestJob

        pending_jobs = await db.execute(
            select(func.count()).select_from(IngestJob).where(
                IngestJob.asset_id == asset.id,
                IngestJob.status.in_(["pending", "processing"]),
            )
        )
        pending_count = pending_jobs.scalar() or 0

        if pending_count > 0:
            return {
                "status": "waiting",
                "pending_jobs": pending_count,
            }

        # Check for failed jobs
        failed_jobs = await db.execute(
            select(func.count()).select_from(IngestJob).where(
                IngestJob.asset_id == asset.id,
                IngestJob.status == "failed",
            )
        )
        failed_count = failed_jobs.scalar() or 0

        if failed_count > 0:
            asset.status = "failed"
            await db.commit()
            return {
                "status": "failed",
                "failed_jobs": failed_count,
            }

        # All jobs completed successfully
        asset.status = "available"
        await db.commit()

        logger.info(f"Asset {asset_id} is now available")
        return {
            "status": "available",
            "asset_id": asset_id,
        }


@shared_task(bind=True, name="app.workers.tasks.ingest.finalize_ingest")
def finalize_ingest(self, asset_id: str):
    """
    Finalize the ingest process for an asset.

    Checks if all jobs completed and updates asset status.

    Args:
        asset_id: The Asset ID
    """
    return asyncio.get_event_loop().run_until_complete(
        _finalize_ingest_async(asset_id)
    )
