"""
AKASHI MAM API - Collection Schemas
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


CollectionType = Literal["manual", "smart", "system"]


# =============================================================================
# Collection Schemas
# =============================================================================


class CollectionCreate(BaseSchema):
    """Schema for creating a collection."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    slug: str | None = Field(None, max_length=255)
    collection_type: CollectionType = "manual"
    filter_query: dict[str, Any] | None = None
    color: str | None = Field(None, max_length=20)
    icon: str | None = Field(None, max_length=50)
    is_public: bool = False
    tenant_code: str | None = Field(None, description="Tenant code (uses 'dev' if not provided)")


class CollectionUpdate(BaseSchema):
    """Schema for updating a collection."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    slug: str | None = Field(None, max_length=255)
    filter_query: dict[str, Any] | None = None
    cover_asset_id: UUID | None = None
    color: str | None = Field(None, max_length=20)
    icon: str | None = Field(None, max_length=50)
    is_public: bool | None = None
    is_locked: bool | None = None


class CollectionRead(BaseSchema):
    """Schema for reading a collection."""

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    slug: str | None
    collection_type: str
    filter_query: dict[str, Any] | None
    cover_asset_id: UUID | None
    color: str | None
    icon: str | None
    is_public: bool
    is_locked: bool
    item_count: int
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class CollectionSummary(BaseSchema):
    """Minimal collection summary for lists."""

    id: UUID
    name: str
    description: str | None
    collection_type: str
    item_count: int
    is_public: bool
    cover_asset_id: UUID | None
    color: str | None
    created_at: datetime


class CollectionListResponse(BaseSchema):
    """Response for collection list endpoint."""

    items: list[CollectionSummary]
    total: int
    page: int
    page_size: int


# =============================================================================
# Collection Item Schemas
# =============================================================================


class CollectionItemCreate(BaseSchema):
    """Schema for adding an asset to a collection."""

    asset_id: UUID
    position: int | None = None
    note: str | None = None


class CollectionItemUpdate(BaseSchema):
    """Schema for updating a collection item."""

    position: int | None = None
    note: str | None = None


class CollectionItemRead(BaseSchema):
    """Schema for reading a collection item."""

    id: UUID
    collection_id: UUID
    asset_id: UUID
    position: int
    added_by: UUID | None
    added_at: datetime
    note: str | None


class CollectionItemWithAsset(BaseSchema):
    """Collection item with embedded asset info."""

    id: UUID
    asset_id: UUID
    position: int
    added_at: datetime
    note: str | None
    # Asset info (denormalized for convenience)
    asset_title: str | None = None
    asset_type: str | None = None
    asset_thumbnail_url: str | None = None
    asset_duration_ms: int | None = None


class CollectionWithItems(CollectionRead):
    """Collection with its items."""

    items: list[CollectionItemWithAsset] = []


class BulkAddItemsRequest(BaseSchema):
    """Request to add multiple assets to a collection."""

    asset_ids: list[UUID] = Field(..., min_length=1, max_length=100)


class ReorderItemsRequest(BaseSchema):
    """Request to reorder items in a collection."""

    item_ids: list[UUID] = Field(..., min_length=1, description="Item IDs in new order")
