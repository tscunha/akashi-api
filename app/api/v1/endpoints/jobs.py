"""
AKASHI MAM API - Jobs Endpoints
Endpoints for monitoring and manually triggering processing jobs.
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, update

from app.api.deps import DbSession
from app.models import Asset, AssetStorageLocation, AssetTechnicalMetadata, IngestJob
from app.schemas import JobSummary, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    db: DbSession,
    status_filter: str | None = Query(None, alias="status"),
    job_type: str | None = Query(None),
    asset_id: UUID | None = Query(None),
    limit: int = Query(50, le=100),
):
    """List processing jobs with filters."""
    query = select(IngestJob).order_by(IngestJob.created_at.desc())

    if status_filter:
        query = query.where(IngestJob.status == status_filter)
    if job_type:
        query = query.where(IngestJob.job_type == job_type)
    if asset_id:
        query = query.where(IngestJob.asset_id == asset_id)

    query = query.limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return [
        JobSummary(
            id=job.id,
            job_type=job.job_type,
            status=job.status,
            progress=job.progress,
            created_at=job.created_at,
            error_message=job.error_message,
        )
        for job in jobs
    ]


@router.post("/process-pending", response_model=MessageResponse)
async def process_pending_jobs(
    db: DbSession,
    limit: int = Query(10, le=50),
    sync: bool = Query(False, description="Process synchronously (blocking)"),
):
    """
    Process pending jobs.
    Use sync=true to process synchronously (useful when Celery is not running).
    """
    result = await db.execute(
        select(IngestJob)
        .where(IngestJob.status == "pending")
        .order_by(IngestJob.priority.desc(), IngestJob.created_at)
        .limit(limit)
    )
    jobs = list(result.scalars().all())

    if not jobs:
        return MessageResponse(message="No pending jobs found")

    dispatched = 0
    errors = []

    for job in jobs:
        try:
            if sync:
                # Process synchronously
                await _process_job_sync(db, job)
            else:
                # Dispatch to Celery
                from app.workers.tasks.metadata import extract_metadata
                from app.workers.tasks.proxy import generate_proxy
                from app.workers.tasks.thumbnail import generate_thumbnail

                if job.job_type == "metadata":
                    extract_metadata.delay(str(job.id), str(job.asset_id), job.input_path)
                elif job.job_type == "proxy":
                    generate_proxy.delay(str(job.id), str(job.asset_id), job.input_path)
                elif job.job_type == "thumbnail":
                    generate_thumbnail.delay(str(job.id), str(job.asset_id), job.input_path)

            dispatched += 1
        except Exception as e:
            errors.append(f"{job.id}: {str(e)}")
            logger.error(f"Failed to process job {job.id}: {e}")

    message = f"Processed {dispatched}/{len(jobs)} jobs"
    if errors:
        message += f". Errors: {len(errors)}"

    return MessageResponse(message=message)


@router.get("/{job_id}", response_model=JobSummary)
async def get_job(job_id: UUID, db: DbSession):
    """Get a specific job by ID."""
    result = await db.execute(select(IngestJob).where(IngestJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobSummary(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        error_message=job.error_message,
    )


@router.post("/{job_id}/retry", response_model=MessageResponse)
async def retry_job(job_id: UUID, db: DbSession):
    """Retry a failed job."""
    result = await db.execute(select(IngestJob).where(IngestJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry failed or cancelled jobs, current status: {job.status}",
        )

    # Reset job
    job.status = "pending"
    job.progress = 0
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    job.worker_id = None

    await db.flush()

    # Try to dispatch to Celery
    try:
        from app.workers.tasks.metadata import extract_metadata
        from app.workers.tasks.proxy import generate_proxy
        from app.workers.tasks.thumbnail import generate_thumbnail

        if job.job_type == "metadata":
            extract_metadata.delay(str(job.id), str(job.asset_id), job.input_path)
        elif job.job_type == "proxy":
            generate_proxy.delay(str(job.id), str(job.asset_id), job.input_path)
        elif job.job_type == "thumbnail":
            generate_thumbnail.delay(str(job.id), str(job.asset_id), job.input_path)

        logger.info(f"Dispatched retry for job {job.id}")
    except Exception as e:
        logger.warning(f"Could not dispatch to Celery: {e}")

    return MessageResponse(message=f"Job {job_id} queued for retry", id=job_id)


async def _process_job_sync(db: DbSession, job: IngestJob):
    """Process a job synchronously using FFmpeg/FFprobe (for when Celery is not available)."""
    import json
    import subprocess
    import tempfile
    from pathlib import Path

    from app.core.config import settings
    from app.models import AssetStorageLocation, AssetTechnicalMetadata
    from app.services.storage_service import StorageService

    job.status = "processing"
    job.started_at = datetime.utcnow()
    await db.flush()

    storage = StorageService()
    temp_input = None
    temp_output = None

    try:
        # Download file from storage
        logger.info(f"Downloading file for job {job.id}: {job.input_path}")
        content = await storage.download_file(
            bucket=storage.bucket_originals,
            path=job.input_path,
        )

        # Write to temp file
        original_ext = Path(job.input_path).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_ext) as f:
            f.write(content)
            temp_input = f.name

        logger.info(f"Processing job {job.id} ({job.job_type}) with temp file: {temp_input}")

        if job.job_type == "metadata":
            # Extract metadata with FFprobe
            cmd = [
                settings.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                temp_input,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                ffprobe_data = json.loads(result.stdout)
                metadata = _parse_ffprobe_output(ffprobe_data)

                # Extract duration (goes to Asset, not TechnicalMetadata)
                duration_ms = metadata.pop("_duration_ms", None)

                # Get asset for tenant_id
                asset_result = await db.execute(select(Asset).where(Asset.id == job.asset_id))
                asset = asset_result.scalar_one_or_none()

                if asset:
                    # Filter only valid TechnicalMetadata fields
                    tech_meta_fields = {
                        k: v for k, v in metadata.items()
                        if v is not None and not k.startswith("_")
                    }

                    # Update or create technical metadata
                    existing = await db.get(AssetTechnicalMetadata, job.asset_id)
                    if existing:
                        for key, value in tech_meta_fields.items():
                            setattr(existing, key, value)
                        existing.ffprobe_raw = ffprobe_data
                        existing.analyzed_at = datetime.utcnow()
                    else:
                        tech_meta = AssetTechnicalMetadata(
                            asset_id=job.asset_id,
                            tenant_id=asset.tenant_id,
                            ffprobe_raw=ffprobe_data,
                            analyzed_at=datetime.utcnow(),
                            analyzer_version="ffprobe",
                            **tech_meta_fields,
                        )
                        db.add(tech_meta)

                    # Update asset duration
                    if duration_ms:
                        asset.duration_ms = duration_ms

                job.result = {**metadata, "duration_ms": duration_ms}
                logger.info(f"Metadata extracted: {metadata.get('video_codec')}, {metadata.get('width')}x{metadata.get('height')}, duration={duration_ms}ms")
            else:
                raise Exception(f"FFprobe failed: {result.stderr}")

        elif job.job_type == "proxy":
            # Generate proxy with FFmpeg
            temp_output = tempfile.mktemp(suffix="_proxy.mp4")
            width, height = settings.proxy_resolution.split("x")

            cmd = [
                settings.ffmpeg_path,
                "-y",
                "-i", temp_input,
                "-c:v", "libx264",
                "-preset", settings.proxy_preset,
                "-crf", str(settings.proxy_crf),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                temp_output,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

            if result.returncode == 0 and Path(temp_output).exists():
                # Upload proxy
                with open(temp_output, "rb") as f:
                    proxy_content = f.read()

                proxy_path = await storage.upload_file(
                    content=proxy_content,
                    filename=f"{job.asset_id}_proxy.mp4",
                    asset_id=str(job.asset_id),
                    tenant_code="dev",
                    purpose="proxy",
                    bucket=storage.bucket_proxies,
                )

                # Get asset for tenant_id
                asset_result = await db.execute(select(Asset).where(Asset.id == job.asset_id))
                asset = asset_result.scalar_one_or_none()

                if asset:
                    # Create storage location
                    storage_location = AssetStorageLocation(
                        asset_id=job.asset_id,
                        tenant_id=asset.tenant_id,
                        storage_type="s3",
                        storage_tier="hot",
                        bucket=storage.bucket_proxies,
                        path=proxy_path,
                        filename=f"{job.asset_id}_proxy.mp4",
                        file_size_bytes=len(proxy_content),
                        purpose="proxy",
                        is_primary=False,
                    )
                    db.add(storage_location)

                job.output_path = proxy_path
                job.result = {"path": proxy_path, "size": len(proxy_content)}
                logger.info(f"Proxy generated: {proxy_path} ({len(proxy_content)} bytes)")
            else:
                raise Exception(f"FFmpeg proxy failed: {result.stderr}")

        elif job.job_type == "thumbnail":
            # Generate thumbnail with FFmpeg
            temp_output = tempfile.mktemp(suffix=".jpg")

            # Get duration for timestamp
            duration_cmd = [
                settings.ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                temp_input,
            ]
            dur_result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=30)
            duration = float(dur_result.stdout.strip()) if dur_result.returncode == 0 else 0

            # Pick timestamp at 10% or 1 second
            timestamp_sec = max(1, duration * 0.1) if duration > 10 else (1 if duration > 1 else 0)
            timestamp = f"{int(timestamp_sec // 3600):02d}:{int((timestamp_sec % 3600) // 60):02d}:{int(timestamp_sec % 60):02d}"

            cmd = [
                settings.ffmpeg_path,
                "-y",
                "-ss", timestamp,
                "-i", temp_input,
                "-vframes", "1",
                "-vf", f"scale={settings.thumbnail_width}:{settings.thumbnail_height}:force_original_aspect_ratio=decrease,pad={settings.thumbnail_width}:{settings.thumbnail_height}:(ow-iw)/2:(oh-ih)/2",
                "-q:v", "2",
                temp_output,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0 and Path(temp_output).exists():
                # Upload thumbnail
                with open(temp_output, "rb") as f:
                    thumb_content = f.read()

                thumb_path = await storage.upload_file(
                    content=thumb_content,
                    filename=f"{job.asset_id}_thumb.jpg",
                    asset_id=str(job.asset_id),
                    tenant_code="dev",
                    purpose="thumbnail",
                    bucket=storage.bucket_thumbnails,
                )

                # Get asset for tenant_id
                asset_result = await db.execute(select(Asset).where(Asset.id == job.asset_id))
                asset = asset_result.scalar_one_or_none()

                if asset:
                    # Create storage location
                    storage_location = AssetStorageLocation(
                        asset_id=job.asset_id,
                        tenant_id=asset.tenant_id,
                        storage_type="s3",
                        storage_tier="hot",
                        bucket=storage.bucket_thumbnails,
                        path=thumb_path,
                        filename=f"{job.asset_id}_thumb.jpg",
                        file_size_bytes=len(thumb_content),
                        purpose="thumbnail",
                        is_primary=False,
                    )
                    db.add(storage_location)

                job.output_path = thumb_path
                job.result = {"path": thumb_path, "size": len(thumb_content)}
                logger.info(f"Thumbnail generated: {thumb_path} ({len(thumb_content)} bytes)")
            else:
                raise Exception(f"FFmpeg thumbnail failed: {result.stderr}")

        # Mark job complete
        job.status = "completed"
        job.progress = 100
        job.completed_at = datetime.utcnow()

        # Check if all jobs for this asset are complete
        result = await db.execute(
            select(IngestJob).where(
                IngestJob.asset_id == job.asset_id,
                IngestJob.status.in_(("pending", "processing")),
                IngestJob.id != job.id,
            )
        )
        pending = list(result.scalars().all())

        if not pending:
            # All jobs complete - update asset status
            asset_result = await db.execute(
                select(Asset).where(Asset.id == job.asset_id)
            )
            asset = asset_result.scalar_one_or_none()
            if asset:
                asset.status = "available"
                logger.info(f"Asset {asset.id} marked as available")

        await db.flush()
        logger.info(f"Job {job.id} ({job.job_type}) completed synchronously")

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        await db.flush()
        logger.error(f"Job {job.id} failed: {e}")
        raise

    finally:
        # Cleanup temp files
        if temp_input and Path(temp_input).exists():
            Path(temp_input).unlink(missing_ok=True)
        if temp_output and Path(temp_output).exists():
            Path(temp_output).unlink(missing_ok=True)


def _parse_ffprobe_output(data: dict) -> dict:
    """Parse FFprobe output into technical metadata fields.

    Returns dict with:
    - Technical metadata fields (for AssetTechnicalMetadata)
    - _duration_ms: duration in milliseconds (for Asset table, prefixed to indicate special handling)
    """
    metadata = {}

    # Get format info
    format_info = data.get("format", {})
    metadata["container_format"] = format_info.get("format_name", "").split(",")[0]
    # Store duration separately (goes in Asset table, not TechnicalMetadata)
    metadata["_duration_ms"] = int(float(format_info.get("duration", 0)) * 1000)

    # Find video and audio streams
    video_stream = None
    audio_stream = None

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and not video_stream:
            video_stream = stream
        elif codec_type == "audio" and not audio_stream:
            audio_stream = stream

    # Video metadata
    if video_stream:
        metadata["width"] = video_stream.get("width")
        metadata["height"] = video_stream.get("height")
        metadata["video_codec"] = video_stream.get("codec_name")
        metadata["video_codec_profile"] = video_stream.get("profile")
        metadata["video_bitrate_bps"] = int(video_stream.get("bit_rate", 0)) or None

        # Frame rate
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            metadata["frame_rate_num"] = int(num)
            metadata["frame_rate_den"] = int(den)
            if int(den) > 0:
                metadata["frame_rate"] = float(num) / float(den)

        # Aspect ratio
        dar = video_stream.get("display_aspect_ratio")
        if dar:
            metadata["aspect_ratio"] = dar

    # Audio metadata
    if audio_stream:
        metadata["audio_codec"] = audio_stream.get("codec_name")
        metadata["audio_sample_rate"] = int(audio_stream.get("sample_rate", 0)) or None
        metadata["audio_channels"] = audio_stream.get("channels")
        metadata["audio_channel_layout"] = audio_stream.get("channel_layout")
        metadata["audio_bitrate_bps"] = int(audio_stream.get("bit_rate", 0)) or None

    return metadata
