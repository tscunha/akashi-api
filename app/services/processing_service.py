"""
AKASHI MAM API - Processing Service
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, IngestJob


class ProcessingService:
    """Service for managing processing jobs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self,
        asset_id: UUID,
        tenant_id: UUID,
        job_type: str,
        input_path: str | None = None,
        priority: int = 5,
        config: dict[str, Any] | None = None,
    ) -> IngestJob:
        """Create a new processing job."""
        job = IngestJob(
            asset_id=asset_id,
            tenant_id=tenant_id,
            job_type=job_type,
            status="pending",
            priority=priority,
            input_path=input_path,
            config=config or {},
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_job(self, job_id: UUID) -> IngestJob | None:
        """Get a job by ID."""
        result = await self.db.execute(
            select(IngestJob).where(IngestJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_jobs_for_asset(self, asset_id: UUID) -> list[IngestJob]:
        """Get all jobs for an asset."""
        result = await self.db.execute(
            select(IngestJob)
            .where(IngestJob.asset_id == asset_id)
            .order_by(IngestJob.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pending_jobs(
        self,
        job_type: str | None = None,
        limit: int = 10,
    ) -> list[IngestJob]:
        """Get pending jobs, ordered by priority."""
        query = select(IngestJob).where(IngestJob.status == "pending")

        if job_type:
            query = query.where(IngestJob.job_type == job_type)

        query = query.order_by(IngestJob.priority.desc(), IngestJob.created_at)
        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def start_job(
        self,
        job: IngestJob,
        worker_id: str,
    ) -> IngestJob:
        """Mark a job as processing."""
        job.status = "processing"
        job.worker_id = worker_id
        job.started_at = datetime.utcnow()
        await self.db.flush()
        return job

    async def update_progress(
        self,
        job: IngestJob,
        progress: int,
    ) -> IngestJob:
        """Update job progress."""
        job.progress = min(max(progress, 0), 100)
        await self.db.flush()
        return job

    async def complete_job(
        self,
        job: IngestJob,
        output_path: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> IngestJob:
        """Mark a job as completed."""
        job.status = "completed"
        job.progress = 100
        job.completed_at = datetime.utcnow()
        if output_path:
            job.output_path = output_path
        if result:
            job.result = result
        await self.db.flush()
        return job

    async def fail_job(
        self,
        job: IngestJob,
        error_message: str,
    ) -> IngestJob:
        """Mark a job as failed."""
        job.status = "failed"
        job.error_message = error_message
        job.completed_at = datetime.utcnow()
        await self.db.flush()
        return job

    async def cancel_job(self, job: IngestJob) -> IngestJob:
        """Cancel a pending or processing job."""
        if job.status in ("pending", "processing"):
            job.status = "cancelled"
            job.completed_at = datetime.utcnow()
            await self.db.flush()
        return job

    async def queue_standard_pipeline(
        self,
        asset: Asset,
        input_path: str,
    ) -> list[IngestJob]:
        """Queue the standard processing pipeline for an asset."""
        jobs = []

        # 1. Metadata extraction (highest priority)
        jobs.append(
            await self.create_job(
                asset_id=asset.id,
                tenant_id=asset.tenant_id,
                job_type="metadata",
                input_path=input_path,
                priority=10,
            )
        )

        # 2. Proxy generation (for video/audio)
        if asset.asset_type in ("video", "audio"):
            jobs.append(
                await self.create_job(
                    asset_id=asset.id,
                    tenant_id=asset.tenant_id,
                    job_type="proxy",
                    input_path=input_path,
                    priority=5,
                )
            )

        # 3. Thumbnail generation (for video/image)
        if asset.asset_type in ("video", "image"):
            jobs.append(
                await self.create_job(
                    asset_id=asset.id,
                    tenant_id=asset.tenant_id,
                    job_type="thumbnail",
                    input_path=input_path,
                    priority=5,
                )
            )

        return jobs

    async def check_asset_processing_complete(self, asset_id: UUID) -> bool:
        """Check if all processing jobs for an asset are complete."""
        result = await self.db.execute(
            select(IngestJob).where(
                IngestJob.asset_id == asset_id,
                IngestJob.status.in_(("pending", "processing")),
            )
        )
        pending_jobs = result.scalars().all()
        return len(list(pending_jobs)) == 0
