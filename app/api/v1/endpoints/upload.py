"""
AKASHI MAM API - Upload/Ingest Endpoints
"""

import hashlib
import mimetypes
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, get_tenant_by_code
from app.models import Asset, AssetStorageLocation, IngestJob
from app.schemas import IngestResponse, JobSummary, UploadResponse
from app.services.storage_service import StorageService


router = APIRouter()


def detect_asset_type(filename: str, content_type: str | None) -> str:
    """Detect asset type from filename and content type."""
    # Video extensions
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".mxf", ".webm", ".wmv", ".flv"}
    # Audio extensions
    audio_exts = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"}
    # Image extensions
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".raw"}
    # Document extensions
    doc_exts = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in video_exts or (content_type and content_type.startswith("video/")):
        return "video"
    elif ext in audio_exts or (content_type and content_type.startswith("audio/")):
        return "audio"
    elif ext in image_exts or (content_type and content_type.startswith("image/")):
        return "image"
    elif ext in doc_exts or (content_type and content_type.startswith("application/pdf")):
        return "document"
    else:
        return "video"  # Default to video


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_file(
    db: DbSession,
    file: UploadFile = File(..., description="File to upload"),
    title: str = Form(..., min_length=1, max_length=500),
    description: str | None = Form(None),
    asset_type: str | None = Form(None),
    tenant_code: str | None = Form(None),
    code: str | None = Form(None),
    generate_proxy: bool = Form(True),
    generate_thumbnail: bool = Form(True),
    extract_metadata: bool = Form(True),
):
    """
    Ingest a file: create asset, upload to storage, and queue processing jobs.
    This is the main endpoint for the ingest client.
    """
    # Get tenant
    tenant = await get_tenant_by_code(db, tenant_code)

    # Detect asset type if not provided
    if not asset_type:
        asset_type = detect_asset_type(file.filename or "", file.content_type)

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Calculate checksum
    checksum = hashlib.sha256(content).hexdigest()

    # Create asset
    asset = Asset(
        tenant_id=tenant.id,
        title=title,
        description=description,
        asset_type=asset_type,
        code=code,
        status="ingesting",
        file_size_bytes=file_size,
        checksum_sha256=checksum,
    )
    db.add(asset)
    await db.flush()

    # Upload to storage
    storage_service = StorageService()
    try:
        storage_path = await storage_service.upload_file(
            content=content,
            filename=file.filename or f"{asset.id}.bin",
            asset_id=str(asset.id),
            tenant_code=tenant.code,
            purpose="original",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )

    # Create storage location record
    storage_location = AssetStorageLocation(
        asset_id=asset.id,
        tenant_id=tenant.id,
        storage_type="s3",
        storage_tier="hot",
        bucket=storage_service.bucket_originals,
        path=storage_path,
        filename=file.filename,
        file_size_bytes=file_size,
        checksum_sha256=checksum,
        purpose="original",
        is_primary=True,
    )
    db.add(storage_location)

    # Update asset with storage path
    asset.primary_storage_path = f"s3://{storage_service.bucket_originals}/{storage_path}"
    asset.status = "processing"

    # Create processing jobs
    jobs = []

    if extract_metadata:
        job = IngestJob(
            asset_id=asset.id,
            tenant_id=tenant.id,
            job_type="metadata",
            status="pending",
            priority=10,  # High priority
            input_path=storage_path,
        )
        db.add(job)
        jobs.append(job)

    if generate_proxy and asset_type in ("video", "audio"):
        job = IngestJob(
            asset_id=asset.id,
            tenant_id=tenant.id,
            job_type="proxy",
            status="pending",
            priority=5,
            input_path=storage_path,
        )
        db.add(job)
        jobs.append(job)

    if generate_thumbnail and asset_type in ("video", "image"):
        job = IngestJob(
            asset_id=asset.id,
            tenant_id=tenant.id,
            job_type="thumbnail",
            status="pending",
            priority=5,
            input_path=storage_path,
        )
        db.add(job)
        jobs.append(job)

    await db.flush()

    # TODO: Dispatch jobs to Celery workers
    # from app.workers.tasks import process_asset
    # process_asset.delay(str(asset.id))

    return IngestResponse(
        asset_id=asset.id,
        status="processing",
        message=f"Asset created and {len(jobs)} jobs queued",
        jobs=[
            JobSummary(
                id=job.id,
                job_type=job.job_type,
                status=job.status,
                progress=0,
                created_at=job.created_at or datetime.utcnow(),
            )
            for job in jobs
        ],
    )


@router.post("/assets/{asset_id}/upload", response_model=UploadResponse)
async def upload_file_to_asset(
    asset_id: UUID,
    db: DbSession,
    file: UploadFile = File(...),
    purpose: str = Form("original"),
):
    """
    Upload a file to an existing asset.
    Used for adding derivatives (proxy, thumbnail) to an asset.
    """
    # Get asset
    query = select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Read file content
    content = await file.read()
    file_size = len(content)
    checksum = hashlib.sha256(content).hexdigest()

    # Upload to appropriate bucket based on purpose
    storage_service = StorageService()

    bucket = {
        "original": storage_service.bucket_originals,
        "proxy": storage_service.bucket_proxies,
        "thumbnail": storage_service.bucket_thumbnails,
    }.get(purpose, storage_service.bucket_originals)

    try:
        storage_path = await storage_service.upload_file(
            content=content,
            filename=file.filename or f"{asset_id}.bin",
            asset_id=str(asset_id),
            tenant_code="dev",  # TODO: Get from asset
            purpose=purpose,
            bucket=bucket,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )

    # Create storage location record
    storage_location = AssetStorageLocation(
        asset_id=asset.id,
        tenant_id=asset.tenant_id,
        storage_type="s3",
        storage_tier="hot",
        bucket=bucket,
        path=storage_path,
        filename=file.filename,
        file_size_bytes=file_size,
        checksum_sha256=checksum,
        purpose=purpose,
        is_primary=(purpose == "original"),
    )
    db.add(storage_location)
    await db.flush()

    return UploadResponse(
        asset_id=asset.id,
        storage_location_id=storage_location.id,
        bucket=bucket,
        path=storage_path,
        file_size_bytes=file_size,
        checksum_sha256=checksum,
        status="uploaded",
    )
