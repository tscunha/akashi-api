"""Scene description model for AI-generated scene analysis."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AssetSceneDescription(Base):
    """Model for storing AI-generated scene descriptions."""

    __tablename__ = "asset_scene_descriptions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    asset_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Timing
    timecode_start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    timecode_end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Description
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # description_embedding is stored as vector(1536) in DB

    # Detections
    objects: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # [{object, confidence, bbox}]
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # [{action, confidence}]
    emotions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # [{emotion, confidence}]
    text_ocr: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Model info
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Full-text search vector (auto-updated by trigger)
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AssetSceneDescription(id={self.id}, asset_id={self.asset_id}, timecode={self.timecode_start_ms})>"

    @property
    def duration_ms(self) -> int:
        """Calculate duration in milliseconds."""
        return self.timecode_end_ms - self.timecode_start_ms


class AIExtractedKeyword(Base):
    """Model for AI-extracted keywords from transcription/vision."""

    __tablename__ = "ai_extracted_keywords"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    asset_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Keyword data
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    keyword_normalized: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )  # topic, entity, action, emotion, object
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ai"
    )  # whisper, vision, llm

    # Temporal context (optional)
    start_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AIExtractedKeyword(id={self.id}, keyword={self.keyword}, source={self.source})>"
