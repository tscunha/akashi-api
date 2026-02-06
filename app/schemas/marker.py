"""
AKASHI MAM API - Marker Schemas
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


MarkerType = Literal["comment", "chapter", "todo", "vfx", "audio", "approval", "cut_point"]
MarkerSource = Literal["manual", "fcpx", "resolve", "premiere", "ai", "import"]


class MarkerBase(BaseSchema):
    """Base schema for marker data."""

    marker_type: MarkerType = "comment"
    name: str | None = Field(None, max_length=255)
    color: str | None = Field(None, max_length=20, pattern=r"^#[0-9A-Fa-f]{6}$|^[a-z]+$")
    start_ms: int = Field(..., ge=0, description="Start time in milliseconds")
    duration_ms: int = Field(0, ge=0, description="Duration in milliseconds (0 for point marker)")
    note: str | None = Field(None, max_length=10000)
    keywords: list[str] | None = None
    source: MarkerSource = "manual"
    extra: dict[str, Any] = Field(default_factory=dict)


class MarkerCreate(MarkerBase):
    """Schema for creating a new marker."""

    pass


class MarkerUpdate(BaseSchema):
    """Schema for updating a marker."""

    marker_type: MarkerType | None = None
    name: str | None = Field(None, max_length=255)
    color: str | None = Field(None, max_length=20)
    start_ms: int | None = Field(None, ge=0)
    duration_ms: int | None = Field(None, ge=0)
    note: str | None = None
    keywords: list[str] | None = None
    source: MarkerSource | None = None
    extra: dict[str, Any] | None = None


class MarkerRead(BaseSchema):
    """Schema for marker in responses."""

    id: UUID
    asset_id: UUID
    marker_type: str = "comment"
    name: str | None = None
    color: str | None = None
    start_ms: int
    duration_ms: int = 0
    note: str | None = None
    keywords: list[str] | None = None
    source: str = "manual"
    source_system_id: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


class MarkerSummary(BaseSchema):
    """Minimal marker for inclusion in asset responses."""

    id: UUID
    marker_type: str = "comment"
    name: str | None = None
    color: str | None = None
    start_ms: int
    duration_ms: int = 0


class MarkerListResponse(BaseSchema):
    """Response for marker list endpoint."""

    items: list[MarkerRead]
    total: int
