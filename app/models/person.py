"""Person model for storing known people for face recognition."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Note: pgvector types are handled as raw SQL, not through SQLAlchemy types


class Person(Base):
    """Model for storing known people for face recognition."""

    __tablename__ = "persons"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)  # actor, presenter, etc
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # IMDB, LinkedIn

    # Reference embedding is stored as vector(512) in DB
    # We don't map it directly, use raw SQL for vector operations

    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Stats
    appearance_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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

    # Relationships
    faces: Mapped[list["AssetFace"]] = relationship(
        "AssetFace",
        back_populates="person",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Person(id={self.id}, name={self.name})>"


class AssetFace(Base):
    """Model for storing detected faces in assets."""

    __tablename__ = "asset_faces"

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

    # Identity (if known)
    person_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Temporal location
    timecode_ms: Mapped[int] = mapped_column(nullable=False, index=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)

    # Bounding box (normalized 0-1)
    bbox_x: Mapped[float | None] = mapped_column(nullable=True)
    bbox_y: Mapped[float | None] = mapped_column(nullable=True)
    bbox_w: Mapped[float | None] = mapped_column(nullable=True)
    bbox_h: Mapped[float | None] = mapped_column(nullable=True)

    # Face embedding is stored as vector(512) in DB
    # We don't map it directly, use raw SQL for vector operations

    # Thumbnail
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Confidence
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    person: Mapped[Person | None] = relationship(
        "Person",
        back_populates="faces",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<AssetFace(id={self.id}, asset_id={self.asset_id}, timecode_ms={self.timecode_ms})>"

    @property
    def bbox(self) -> dict[str, float] | None:
        """Return bounding box as dict."""
        if self.bbox_x is not None:
            return {
                "x": float(self.bbox_x),
                "y": float(self.bbox_y),
                "w": float(self.bbox_w),
                "h": float(self.bbox_h),
            }
        return None
