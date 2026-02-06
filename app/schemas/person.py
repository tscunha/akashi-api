"""Pydantic schemas for person and face endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalized bounding box (0-1)."""

    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    w: float = Field(..., ge=0, le=1)
    h: float = Field(..., ge=0, le=1)


class PersonCreate(BaseModel):
    """Schema for creating a person."""

    name: str = Field(..., max_length=255)
    role: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=255)
    metadata: dict = Field(default_factory=dict)


class PersonUpdate(BaseModel):
    """Schema for updating a person."""

    name: str | None = Field(None, max_length=255)
    role: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=255)
    metadata: dict | None = None
    thumbnail_url: str | None = None


class PersonRead(BaseModel):
    """Schema for reading a person."""

    id: UUID
    tenant_id: UUID
    name: str
    role: str | None
    external_id: str | None
    metadata: dict
    thumbnail_url: str | None
    appearance_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PersonSummary(BaseModel):
    """Brief person info for face responses."""

    id: UUID
    name: str
    role: str | None
    thumbnail_url: str | None

    model_config = {"from_attributes": True}


class FaceCreate(BaseModel):
    """Schema for creating a detected face."""

    timecode_ms: int = Field(..., ge=0)
    duration_ms: int | None = Field(None, ge=0)
    bbox: BoundingBox | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    person_id: UUID | None = None


class FaceRead(BaseModel):
    """Schema for reading a detected face."""

    id: UUID
    asset_id: UUID
    tenant_id: UUID
    person_id: UUID | None
    timecode_ms: int
    duration_ms: int | None
    bbox: BoundingBox | None
    thumbnail_url: str | None
    confidence: float | None
    person: PersonSummary | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FaceIdentifyRequest(BaseModel):
    """Request to identify a face."""

    face_id: UUID
    person_id: UUID


class FaceSearchRequest(BaseModel):
    """Request to search by face image."""

    image_base64: str = Field(..., description="Base64 encoded face image")
    min_confidence: float = Field(default=0.7, ge=0, le=1)
    limit: int = Field(default=20, ge=1, le=100)


class FaceSearchResult(BaseModel):
    """Result of face similarity search."""

    face: FaceRead
    similarity: float
    asset_id: UUID
    asset_title: str | None
