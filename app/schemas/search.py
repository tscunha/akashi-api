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


# =====================================================
# Multimodal Search Schemas
# =====================================================


class SearchMode(BaseSchema):
    """Available search modes for multimodal search."""

    transcription: bool = True
    face: bool = True
    scene: bool = True
    keywords: bool = True
    metadata: bool = True


class SearchFilters(BaseSchema):
    """Filters for multimodal search."""

    asset_type: AssetType | None = None
    status: AssetStatus | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    collections: list[UUID] | None = None
    persons: list[UUID] | None = None  # Filter by known people
    min_duration_ms: int | None = None
    max_duration_ms: int | None = None


class MultimodalSearchRequest(BaseSchema):
    """Request for multimodal search."""

    query: str = Field(..., min_length=1, max_length=500)
    modes: SearchMode = Field(default_factory=SearchMode)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    face_image: str | None = Field(None, description="Base64 encoded face image for face search")
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class MatchInfo(BaseSchema):
    """Information about a single match in multimodal search."""

    type: Literal["transcription", "face", "scene", "keyword", "metadata"]
    timecode_ms: int | None = None
    text: str | None = None
    description: str | None = None
    person_name: str | None = None
    keyword: str | None = None
    score: float


class MultimodalSearchResult(BaseSchema):
    """A single result from multimodal search."""

    asset_id: UUID
    title: str | None
    description: str | None
    asset_type: str
    status: str
    thumbnail_url: str | None
    duration_ms: int | None
    matches: list[MatchInfo]
    combined_score: float
    created_at: datetime


class MultimodalSearchResponse(BaseSchema):
    """Response from multimodal search."""

    query: str
    total: int
    limit: int
    offset: int
    search_time_ms: int
    results: list[MultimodalSearchResult]
    modes_used: list[str]
