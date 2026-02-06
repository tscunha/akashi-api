"""
AKASHI MAM API - Marker Model
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


MarkerType = Literal["comment", "chapter", "todo", "vfx", "audio", "approval", "cut_point"]
MarkerSource = Literal["manual", "fcpx", "resolve", "premiere", "ai", "import"]


class AssetMarker(Base):
    """
    Timeline markers for video/audio assets.
    Supports various marker types (chapter, comment, todo, etc.).
    """

    __tablename__ = "asset_markers"
    __table_args__ = (
        Index("idx_markers_asset", "asset_id"),
        Index("idx_markers_temporal", "asset_id", "start_ms"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # References
    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )

    # Marker metadata
    marker_type: Mapped[str] = mapped_column(
        String(50),
        default="comment",
        server_default="comment",
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Hex color

    # Temporal position
    start_ms: Mapped[int] = mapped_column(nullable=False)
    duration_ms: Mapped[int] = mapped_column(default=0, server_default="0")

    # Content
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
    )

    # Source tracking
    source: Mapped[str] = mapped_column(
        String(50),
        default="manual",
        server_default="manual",
    )
    source_system_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )  # Original ID from source system (e.g., FCPX marker ID)

    # Audit
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default="now()",
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default="now()",
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Extra data (for NLE-specific metadata)
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")  # noqa: F821

    def __repr__(self) -> str:
        return f"<AssetMarker(id={self.id}, type='{self.marker_type}', start={self.start_ms}ms)>"

    @property
    def end_ms(self) -> int:
        """Calculate end position in milliseconds."""
        return self.start_ms + self.duration_ms

    @property
    def has_duration(self) -> bool:
        """Check if this marker has a duration (range marker)."""
        return self.duration_ms > 0
