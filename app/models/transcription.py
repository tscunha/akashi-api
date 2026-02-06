"""Transcription model for storing audio/video transcriptions."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AssetTranscription(Base):
    """Model for storing transcriptions of audio/video assets."""

    __tablename__ = "asset_transcriptions"

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

    # Language
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="pt")

    # Content
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    segments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # [{start_ms, end_ms, text, confidence}]

    # Generated subtitles
    srt_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    vtt_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_avg: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    # Processing info
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Full-text search vector (auto-updated by trigger)
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<AssetTranscription(id={self.id}, asset_id={self.asset_id}, language={self.language})>"

    def to_srt(self) -> str:
        """Generate SRT subtitle format from segments."""
        if not self.segments:
            return ""

        lines = []
        for i, segment in enumerate(self.segments, 1):
            start_ms = segment.get("start_ms", 0)
            end_ms = segment.get("end_ms", start_ms + 1000)
            text = segment.get("text", "").strip()

            if not text:
                continue

            start_time = self._ms_to_srt_time(start_ms)
            end_time = self._ms_to_srt_time(end_ms)

            lines.append(str(i))
            lines.append(f"{start_time} --> {end_time}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    def to_vtt(self) -> str:
        """Generate WebVTT subtitle format from segments."""
        if not self.segments:
            return "WEBVTT\n\n"

        lines = ["WEBVTT", ""]
        for segment in self.segments:
            start_ms = segment.get("start_ms", 0)
            end_ms = segment.get("end_ms", start_ms + 1000)
            text = segment.get("text", "").strip()

            if not text:
                continue

            start_time = self._ms_to_vtt_time(start_ms)
            end_time = self._ms_to_vtt_time(end_ms)

            lines.append(f"{start_time} --> {end_time}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _ms_to_srt_time(ms: int) -> str:
        """Convert milliseconds to SRT time format (HH:MM:SS,mmm)."""
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        milliseconds = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    @staticmethod
    def _ms_to_vtt_time(ms: int) -> str:
        """Convert milliseconds to WebVTT time format (HH:MM:SS.mmm)."""
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        milliseconds = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
