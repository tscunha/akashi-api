"""
AKASHI MAM API - Metadata Extraction Worker
"""

import asyncio
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import UUID

from celery import shared_task

from app.core.config import settings
from app.core.database import get_db_context
from app.models import Asset, AssetTechnicalMetadata, IngestJob
from app.services import StorageService


def run_ffprobe(file_path: str) -> dict:
    """Run FFprobe and return parsed output."""
    cmd = [
        settings.ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    return {}


def parse_ffprobe_output(data: dict) -> dict:
    """Parse FFprobe output into technical metadata fields."""
    metadata = {}

    # Get format info
    format_info = data.get("format", {})
    metadata["container_format"] = format_info.get("format_name", "").split(",")[0]
    metadata["duration_ms"] = int(float(format_info.get("duration", 0)) * 1000)

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

        # Bit depth
        metadata["bit_depth"] = video_stream.get("bits_per_raw_sample")
        if metadata["bit_depth"]:
            metadata["bit_depth"] = int(metadata["bit_depth"])

        # Color space
        metadata["color_space"] = video_stream.get("color_space")

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
        metadata["audio_bit_depth"] = audio_stream.get("bits_per_sample")
        if metadata["audio_bit_depth"]:
            metadata["audio_bit_depth"] = int(metadata["audio_bit_depth"])

    return metadata


async def _extract_metadata_async(job_id: str, asset_id: str, input_path: str):
    """Async implementation of metadata extraction."""
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

            # Write to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as f:
                f.write(content)
                temp_path = f.name

            # Run FFprobe
            ffprobe_output = run_ffprobe(temp_path)

            # Parse output
            metadata = parse_ffprobe_output(ffprobe_output)

            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

            # Update or create technical metadata
            existing = await db.get(AssetTechnicalMetadata, asset.id)
            if existing:
                for key, value in metadata.items():
                    if value is not None:
                        setattr(existing, key, value)
                existing.ffprobe_raw = ffprobe_output
                existing.analyzed_at = datetime.utcnow()
                existing.analyzer_version = "ffprobe"
            else:
                tech_meta = AssetTechnicalMetadata(
                    asset_id=asset.id,
                    tenant_id=asset.tenant_id,
                    ffprobe_raw=ffprobe_output,
                    analyzed_at=datetime.utcnow(),
                    analyzer_version="ffprobe",
                    **{k: v for k, v in metadata.items() if v is not None},
                )
                db.add(tech_meta)

            # Update asset duration if extracted
            if metadata.get("duration_ms"):
                asset.duration_ms = metadata["duration_ms"]

            # Complete job
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.utcnow()
            job.result = metadata

            await db.commit()
            return {"status": "completed", "metadata": metadata}

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            return {"error": str(e)}


@shared_task(bind=True, name="app.workers.tasks.metadata.extract_metadata")
def extract_metadata(self, job_id: str, asset_id: str, input_path: str):
    """
    Extract technical metadata from a media file using FFprobe.

    Args:
        job_id: The IngestJob ID
        asset_id: The Asset ID
        input_path: Path to the file in storage
    """
    return asyncio.get_event_loop().run_until_complete(
        _extract_metadata_async(job_id, asset_id, input_path)
    )
