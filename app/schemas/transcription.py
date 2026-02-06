"""Pydantic schemas for transcription endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    """A single segment of transcription with timing."""

    start_ms: int = Field(..., description="Start time in milliseconds")
    end_ms: int = Field(..., description="End time in milliseconds")
    text: str = Field(..., description="Transcribed text")
    confidence: float | None = Field(None, ge=0, le=1, description="Confidence score")


class TranscriptionCreate(BaseModel):
    """Schema for creating a transcription (usually from Whisper)."""

    language: str = Field(default="pt", max_length=10)
    full_text: str | None = None
    segments: list[TranscriptionSegment] = Field(default_factory=list)
    model_version: str | None = None
    processing_time_ms: int | None = None


class TranscriptionRead(BaseModel):
    """Schema for reading a transcription."""

    id: UUID
    asset_id: UUID
    tenant_id: UUID
    language: str
    full_text: str | None
    segments: list[TranscriptionSegment]
    srt_content: str | None
    vtt_content: str | None
    duration_ms: int | None
    word_count: int | None
    confidence_avg: float | None
    model_version: str | None
    processing_time_ms: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TranscriptionSummary(BaseModel):
    """Brief transcription info for asset responses."""

    id: UUID
    language: str
    word_count: int | None
    confidence_avg: float | None
    has_subtitles: bool

    model_config = {"from_attributes": True}


class TranscribeRequest(BaseModel):
    """Request to start transcription of an asset."""

    language: str = Field(default="pt", description="Language code (pt, en, es, etc)")
    model: str = Field(default="large-v3", description="Whisper model to use")


class TranscribeResponse(BaseModel):
    """Response after starting transcription."""

    job_id: UUID
    asset_id: UUID
    status: str
    message: str
