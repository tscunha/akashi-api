"""Pydantic schemas for scene description endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DetectedObject(BaseModel):
    """An object detected in a scene."""

    object: str
    confidence: float = Field(..., ge=0, le=1)
    bbox: dict | None = None


class DetectedAction(BaseModel):
    """An action detected in a scene."""

    action: str
    confidence: float = Field(..., ge=0, le=1)


class DetectedEmotion(BaseModel):
    """An emotion detected in a scene."""

    emotion: str
    confidence: float = Field(..., ge=0, le=1)


class SceneDescriptionCreate(BaseModel):
    """Schema for creating a scene description."""

    timecode_start_ms: int = Field(..., ge=0)
    timecode_end_ms: int = Field(..., ge=0)
    description: str
    objects: list[DetectedObject] = Field(default_factory=list)
    actions: list[DetectedAction] = Field(default_factory=list)
    emotions: list[DetectedEmotion] = Field(default_factory=list)
    text_ocr: str | None = None
    model_version: str | None = None


class SceneDescriptionRead(BaseModel):
    """Schema for reading a scene description."""

    id: UUID
    asset_id: UUID
    tenant_id: UUID
    timecode_start_ms: int
    timecode_end_ms: int
    duration_ms: int
    description: str
    objects: list[DetectedObject]
    actions: list[DetectedAction]
    emotions: list[DetectedEmotion]
    text_ocr: str | None
    model_version: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIKeywordCreate(BaseModel):
    """Schema for creating an AI-extracted keyword."""

    keyword: str = Field(..., max_length=255)
    category: str | None = Field(None, max_length=100)
    confidence: float | None = Field(None, ge=0, le=1)
    source: str = Field(default="ai", max_length=50)
    start_ms: int | None = Field(None, ge=0)
    end_ms: int | None = Field(None, ge=0)


class AIKeywordRead(BaseModel):
    """Schema for reading an AI-extracted keyword."""

    id: UUID
    asset_id: UUID
    keyword: str
    keyword_normalized: str
    category: str | None
    confidence: float | None
    source: str
    start_ms: int | None
    end_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DescribeRequest(BaseModel):
    """Request to start scene description of an asset."""

    interval_seconds: int = Field(default=10, ge=1, le=60)
    model: str = Field(default="gpt-4-vision-preview")


class DescribeResponse(BaseModel):
    """Response after starting scene description."""

    job_id: UUID
    asset_id: UUID
    status: str
    message: str
