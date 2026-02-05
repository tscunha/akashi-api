"""
AKASHI MAM API - Upload/Ingest Schemas
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema
from app.schemas.asset import AssetType


JobType = Literal["proxy", "thumbnail", "metadata", "transcode", "transcript"]
JobStatus = Literal["pending", "processing", "completed", "failed", "cancelled"]


class IngestRequest(BaseSchema):
    """Request schema for ingest endpoint (multipart form)."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    asset_type: AssetType | None = None  # Auto-detected if not provided
    tenant_code: str | None = Field(
        None,
        description="Tenant code (uses 'dev' if not provided)",
    )
    code: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    # Processing options
    generate_proxy: bool = True
    generate_thumbnail: bool = True
    extract_metadata: bool = True


class IngestResponse(BaseSchema):
    """Response schema for ingest endpoint."""

    asset_id: UUID
    status: str
    message: str
    jobs: list["JobSummary"] = []


class UploadResponse(BaseSchema):
    """Response schema for upload endpoint."""

    asset_id: UUID
    storage_location_id: UUID
    bucket: str
    path: str
    file_size_bytes: int
    checksum_sha256: str | None
    status: str


class JobSummary(BaseSchema):
    """Summary of a processing job."""

    id: UUID
    job_type: JobType
    status: JobStatus
    progress: int
    created_at: datetime


class JobRead(BaseSchema):
    """Full job details."""

    id: UUID
    asset_id: UUID
    job_type: JobType
    status: JobStatus
    priority: int
    progress: int
    error_message: str | None
    worker_id: str | None
    input_path: str | None
    output_path: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    config: dict[str, Any]
    result: dict[str, Any]


class PresignedUrlResponse(BaseSchema):
    """Response with presigned URL for download."""

    url: str
    expires_at: datetime
    filename: str
    content_type: str
    file_size_bytes: int | None
