"""
AKASHI MAM API - Proxy Generation Worker
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


def run_ffmpeg_proxy(input_path: str, output_path: str, resolution: str = "1280x720") -> bool:
    """Generate a proxy file using FFmpeg."""
    width, height = resolution.split("x")

    cmd = [
        settings.ffmpeg_path,
        "-y",  # Overwrite output
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", settings.proxy_preset,
        "-crf", str(settings.proxy_crf),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


async def _generate_proxy_async(job_id: str, asset_id: str, input_path: str):
    """Async implementation of proxy generation."""
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
            temp_output = tempfile.mktemp(suffix="_proxy.mp4")

            # Run FFmpeg
            success = run_ffmpeg_proxy(
                temp_input,
                temp_output,
                settings.proxy_resolution,
            )

            if not success:
                raise Exception("FFmpeg proxy generation failed")

            # Read output file
            with open(temp_output, "rb") as f:
                proxy_content = f.read()

            # Upload proxy to storage
            proxy_path = await storage.upload_file(
                content=proxy_content,
                filename=f"{asset.id}_proxy.mp4",
                asset_id=str(asset.id),
                tenant_code="dev",  # TODO: Get from asset tenant
                purpose="proxy",
                bucket=storage.bucket_proxies,
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
                bucket=storage.bucket_proxies,
                path=proxy_path,
                filename=f"{asset.id}_proxy.mp4",
                file_size_bytes=len(proxy_content),
                purpose="proxy",
                is_primary=False,
            )
            db.add(storage_location)

            # Complete job
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.utcnow()
            job.output_path = proxy_path
            job.result = {
                "bucket": storage.bucket_proxies,
                "path": proxy_path,
                "size": len(proxy_content),
            }

            await db.commit()
            return {"status": "completed", "path": proxy_path}

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            return {"error": str(e)}


@shared_task(bind=True, name="app.workers.tasks.proxy.generate_proxy")
def generate_proxy(self, job_id: str, asset_id: str, input_path: str):
    """
    Generate a proxy (lower resolution) version of a video.

    Args:
        job_id: The IngestJob ID
        asset_id: The Asset ID
        input_path: Path to the original file in storage
    """
    return asyncio.get_event_loop().run_until_complete(
        _generate_proxy_async(job_id, asset_id, input_path)
    )
