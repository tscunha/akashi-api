"""
AKASHI MAM API - Keyword Model
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


KeywordSource = Literal["manual", "fcpx", "resolve", "premiere", "ai", "import"]


class AssetKeyword(Base):
    """
    Keywords associated with assets.
    Supports temporal keywords (with start_ms/end_ms) for video/audio.
    """

    __tablename__ = "asset_keywords"
    __table_args__ = (
        Index("idx_keywords_asset", "asset_id"),
        Index("idx_keywords_search", "tenant_id", "keyword_normalized"),
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

    # Keyword content
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    keyword_normalized: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )  # Auto-filled by DB trigger

    # Temporal range (optional - for video/audio keywords)
    start_ms: Mapped[int | None] = mapped_column(nullable=True)
    end_ms: Mapped[int | None] = mapped_column(nullable=True)

    # Additional metadata
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(50),
        default="manual",
        server_default="manual",
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
    )  # For AI-generated keywords

    # Audit
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default="now()",
        default=datetime.utcnow,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")  # noqa: F821

    def __repr__(self) -> str:
        time_range = ""
        if self.start_ms is not None:
            time_range = f", start={self.start_ms}ms"
            if self.end_ms is not None:
                time_range += f", end={self.end_ms}ms"
        return f"<AssetKeyword(id={self.id}, keyword='{self.keyword}'{time_range})>"

    @property
    def is_temporal(self) -> bool:
        """Check if this keyword has a time range."""
        return self.start_ms is not None
