"""
AKASHI MAM API - Search Schemas
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


AssetType = Literal["video", "audio", "image", "document", "sequence"]
AssetStatus = Literal["ingesting", "processing", "available", "review", "archived", "deleted"]


class SearchQuery(BaseSchema):
    """Search query parameters."""

    q: str = Field(..., min_length=2, description="Search term")
    asset_type: AssetType | None = Field(None, description="Filter by asset type")
    status: AssetStatus | None = Field(None, description="Filter by status")
    date_from: datetime | None = Field(None, description="Created after this date")
    date_to: datetime | None = Field(None, description="Created before this date")
    tenant_code: str | None = Field(None, description="Filter by tenant")


class SearchResult(BaseSchema):
    """Individual search result."""

    id: UUID
    title: str
    description: str | None
    asset_type: str
    status: str
    duration_ms: int | None
    file_size_bytes: int | None
    thumbnail_url: str | None
    created_at: datetime

    # Search relevance
    rank: float | None = None
    headline: str | None = None  # Highlighted snippet


class SearchResponse(BaseSchema):
    """Search response with results and metadata."""

    query: str
    total: int
    page: int
    page_size: int
    results: list[SearchResult]
    # Search metadata
    search_time_ms: int | None = None
    suggestions: list[str] = []


class SearchSuggestion(BaseSchema):
    """Search suggestion/autocomplete item."""

    text: str
    type: str  # 'title', 'keyword', 'collection'
    count: int | None = None
