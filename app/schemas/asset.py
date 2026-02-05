"""
AKASHI MAM API - Asset Schemas
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


# Type definitions
AssetType = Literal["video", "audio", "image", "document", "sequence"]
AssetStatus = Literal["ingesting", "processing", "available", "review", "archived", "deleted"]
Visibility = Literal["private", "internal", "public"]
PublishStatus = Literal["draft", "ready", "published", "unpublished"]
StoragePurpose = Literal["original", "proxy", "thumbnail", "sprite", "hls", "dash"]


class StorageLocationRead(BaseSchema):
    """Storage location in response."""

    id: UUID
    storage_type: str
    storage_tier: str | None
    bucket: str | None
    path: str | None
    filename: str | None
    url: str | None
    file_size_bytes: int | None
    purpose: str
    is_primary: bool
    is_accessible: bool
    status: str
    created_at: datetime


class TechnicalMetadataRead(BaseSchema):
    """Technical metadata in response."""

    width: int | None
    height: int | None
    frame_rate: float | None
    duration_ms: int | None
    video_codec: str | None
    audio_codec: str | None
    audio_channels: int | None
    container_format: str | None
    resolution_category: str | None
    bit_depth: int | None
    analyzed_at: datetime | None


class AssetBase(BaseSchema):
    """Base schema for asset data."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    asset_type: AssetType
    code: str | None = Field(None, max_length=100)
    slug: str | None = Field(None, max_length=255)
    duration_ms: int | None = None
    recorded_at: datetime | None = None
    content_rating: str | None = None
    visibility: Visibility = "internal"
    extra: dict[str, Any] = Field(default_factory=dict)


class AssetCreate(AssetBase):
    """Schema for creating an asset."""

    tenant_code: str | None = Field(
        None,
        description="Tenant code (uses 'dev' if not provided)",
    )
    parent_id: UUID | None = None
    external_ids: dict[str, Any] = Field(default_factory=dict)


class AssetUpdate(BaseSchema):
    """Schema for updating an asset."""

    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    code: str | None = Field(None, max_length=100)
    slug: str | None = Field(None, max_length=255)
    content_rating: str | None = None
    visibility: Visibility | None = None
    status: AssetStatus | None = None
    publish_status: PublishStatus | None = None
    extra: dict[str, Any] | None = None


class AssetRead(AssetBase):
    """Schema for reading an asset."""

    id: UUID
    tenant_id: UUID
    parent_id: UUID | None
    external_ids: dict[str, Any]
    derivative_type: str | None
    status: AssetStatus
    publish_status: PublishStatus
    primary_storage_path: str | None
    file_size_bytes: int | None
    checksum_sha256: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    # Nested
    storage_locations: list[StorageLocationRead] = []
    technical_metadata: TechnicalMetadataRead | None = None


class AssetSummary(BaseSchema):
    """Minimal asset summary for lists."""

    id: UUID
    title: str
    asset_type: AssetType
    status: AssetStatus
    duration_ms: int | None
    file_size_bytes: int | None
    thumbnail_url: str | None = None
    created_at: datetime


class AssetListResponse(BaseSchema):
    """Response for asset list endpoint."""

    items: list[AssetSummary]
    total: int
    page: int
    page_size: int
    pages: int
