"""
AKASHI MAM API - Thumbnail Generation Worker
"""

import asyncio
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import UUID

from celery import shared_task

from app.core.config import settings
from app.core.database import get_db_context
from app.models import Asset, AssetStorageLocation, IngestJob
from app.services import StorageService


def run_ffmpeg_thumbnail(
    input_path: str,
    output_path: str,
    width: int = 320,
    height: int = 180,
    timestamp: str = "00:00:01",
) -> bool:
    """Extract a thumbnail frame using FFmpeg."""
    cmd = [
        settings.ffmpeg_path,
        "-y",  # Overwrite output
        "-ss", timestamp,  # Seek to timestamp
        "-i", input_path,
        "-vframes", "1",  # Extract one frame
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-q:v", "2",  # JPEG quality
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def get_video_duration(input_path: str) -> float:
    """Get video duration in seconds using FFprobe."""
    cmd = [
        settings.ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        pass

    return 0.0


async def _generate_thumbnail_async(job_id: str, asset_id: str, input_path: str):
    """Async implementation of thumbnail generation."""
    storage = StorageService()

    async with get_db_context() as db:
        # Get job
        job = await db.get(IngestJob, UUID(job_id))
        if not job:
            return {"error": "Job not found"}

        # Get asset
        asset = await db.get(Asset, UUID(asset_id))
        if not asset:
            job.status = "failed"
            job.error_message = "Asset not found"
            await db.commit()
            return {"error": "Asset not found"}

        # Update job status
        job.status = "processing"
        job.started_at = datetime.utcnow()
        await db.commit()

        try:
            # Download file to temp location
            content = await storage.download_file(
                bucket=storage.bucket_originals,
                path=input_path,
            )

            # Get original extension
            original_ext = Path(input_path).suffix or ".mp4"

            # Write to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=original_ext) as f:
                f.write(content)
                temp_input = f.name

            # Create output temp file
            temp_output = tempfile.mktemp(suffix=".jpg")

            # Get video duration to pick a good timestamp
            duration = get_video_duration(temp_input)

            # Pick timestamp at 10% of video or 1 second, whichever is greater
            if duration > 10:
                timestamp_seconds = duration * 0.1
            elif duration > 1:
                timestamp_seconds = 1
            else:
                timestamp_seconds = 0

            # Format timestamp
            hours = int(timestamp_seconds // 3600)
            minutes = int((timestamp_seconds % 3600) // 60)
            seconds = int(timestamp_seconds % 60)
            timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            # Run FFmpeg
            success = run_ffmpeg_thumbnail(
                temp_input,
                temp_output,
                settings.thumbnail_width,
                settings.thumbnail_height,
                timestamp,
            )

            if not success:
                # Try with timestamp 0 if first attempt failed
                success = run_ffmpeg_thumbnail(
                    temp_input,
                    temp_output,
                    settings.thumbnail_width,
                    settings.thumbnail_height,
                    "00:00:00",
                )

            if not success:
                raise Exception("FFmpeg thumbnail generation failed")

            # Read output file
            with open(temp_output, "rb") as f:
                thumbnail_content = f.read()

            # Upload thumbnail to storage
            thumbnail_path = await storage.upload_file(
                content=thumbnail_content,
                filename=f"{asset.id}_thumb.jpg",
                asset_id=str(asset.id),
                tenant_code="dev",  # TODO: Get from asset tenant
                purpose="thumbnail",
                bucket=storage.bucket_thumbnails,
            )

            # Clean up temp files
            Path(temp_input).unlink(missing_ok=True)
            Path(temp_output).unlink(missing_ok=True)

            # Create storage location record
            storage_location = AssetStorageLocation(
                asset_id=asset.id,
                tenant_id=asset.tenant_id,
                storage_type="s3",
                storage_tier="hot",
                bucket=storage.bucket_thumbnails,
                path=thumbnail_path,
                filename=f"{asset.id}_thumb.jpg",
                file_size_bytes=len(thumbnail_content),
                purpose="thumbnail",
                is_primary=False,
            )
            db.add(storage_location)

            # Complete job
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.utcnow()
            job.output_path = thumbnail_path
            job.result = {
                "bucket": storage.bucket_thumbnails,
                "path": thumbnail_path,
                "size": len(thumbnail_content),
                "width": settings.thumbnail_width,
                "height": settings.thumbnail_height,
            }

            await db.commit()
            return {"status": "completed", "path": thumbnail_path}

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            return {"error": str(e)}


@shared_task(bind=True, name="app.workers.tasks.thumbnail.generate_thumbnail")
def generate_thumbnail(self, job_id: str, asset_id: str, input_path: str):
    """
    Generate a thumbnail image from a video.

    Args:
        job_id: The IngestJob ID
        asset_id: The Asset ID
        input_path: Path to the original file in storage
    """
    return asyncio.get_event_loop().run_until_complete(
        _generate_thumbnail_async(job_id, asset_id, input_path)
    )
