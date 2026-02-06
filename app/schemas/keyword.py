"""
AKASHI MAM API - Keyword Schemas
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


KeywordSource = Literal["manual", "fcpx", "resolve", "premiere", "ai", "import"]


class KeywordBase(BaseSchema):
    """Base schema for keyword data."""

    keyword: str = Field(..., min_length=1, max_length=255)
    start_ms: int | None = Field(None, ge=0, description="Start time in milliseconds")
    end_ms: int | None = Field(None, ge=0, description="End time in milliseconds")
    note: str | None = Field(None, max_length=5000)
    source: KeywordSource = "manual"
    confidence: Decimal | None = Field(None, ge=0, le=1, description="Confidence score (0-1)")

    @field_validator("end_ms")
    @classmethod
    def validate_end_after_start(cls, v, info):
        if v is not None and info.data.get("start_ms") is not None:
            if v < info.data["start_ms"]:
                raise ValueError("end_ms must be greater than or equal to start_ms")
        return v


class KeywordCreate(KeywordBase):
    """Schema for creating a new keyword."""

    pass


class KeywordUpdate(BaseSchema):
    """Schema for updating a keyword."""

    keyword: str | None = Field(None, min_length=1, max_length=255)
    start_ms: int | None = Field(None, ge=0)
    end_ms: int | None = Field(None, ge=0)
    note: str | None = None
    source: KeywordSource | None = None
    confidence: Decimal | None = Field(None, ge=0, le=1)


class KeywordRead(BaseSchema):
    """Schema for keyword in responses."""

    id: UUID
    asset_id: UUID
    keyword: str
    keyword_normalized: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    note: str | None = None
    source: str = "manual"
    confidence: Decimal | None = None
    created_by: UUID | None = None
    created_at: datetime


class KeywordSummary(BaseSchema):
    """Minimal keyword for inclusion in asset responses."""

    id: UUID
    keyword: str
    start_ms: int | None = None
    end_ms: int | None = None
    source: str = "manual"


class KeywordSearchResult(BaseSchema):
    """Keyword search result with asset info."""

    id: UUID
    asset_id: UUID
    keyword: str
    start_ms: int | None = None
    end_ms: int | None = None
    asset_title: str | None = None
    asset_type: str | None = None


class KeywordListResponse(BaseSchema):
    """Response for keyword list endpoint."""

    items: list[KeywordRead]
    total: int
