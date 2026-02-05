"""
AKASHI MAM API - Asset Model
"""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import BigInteger, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ExtraMixin, SoftDeleteMixin, TimestampMixin


AssetType = Literal["video", "audio", "image", "document", "sequence"]
DerivativeType = Literal["proxy", "thumbnail", "clip", "export", "transcode"]
AssetStatus = Literal["ingesting", "processing", "available", "review", "archived", "deleted"]
Visibility = Literal["private", "internal", "public"]
PublishStatus = Literal["draft", "ready", "published", "unpublished"]


class Asset(Base, TimestampMixin, SoftDeleteMixin, ExtraMixin):
    """
    Asset model representing media files.
    This is a partitioned table in PostgreSQL.
    """

    __tablename__ = "assets"
    __table_args__ = (
        Index("idx_assets_tenant_status", "tenant_id", "status"),
        Index("idx_assets_tenant_type", "tenant_id", "asset_type"),
        {"postgresql_partition_by": "RANGE (partition_date)"},
    )

    # Primary key (composite with partition_date)
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    partition_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
        server_default="CURRENT_DATE",
    )

    # Tenant
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    # Parent (for derivatives)
    parent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Identification
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )

    # Type and classification
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    derivative_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Basic metadata
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Temporal
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Classification
    primary_category_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    content_rating: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="ingesting",
        server_default="ingesting",
    )
    visibility: Mapped[str] = mapped_column(
        String(50),
        default="internal",
        server_default="internal",
    )
    publish_status: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        server_default="draft",
    )

    # Storage
    primary_storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Audit
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(  # noqa: F821
        "Tenant",
        back_populates="assets",
    )
    storage_locations: Mapped[list["AssetStorageLocation"]] = relationship(  # noqa: F821
        "AssetStorageLocation",
        back_populates="asset",
        lazy="selectin",
    )
    technical_metadata: Mapped["AssetTechnicalMetadata | None"] = relationship(  # noqa: F821
        "AssetTechnicalMetadata",
        back_populates="asset",
        uselist=False,
        lazy="selectin",
    )
    ingest_jobs: Mapped[list["IngestJob"]] = relationship(  # noqa: F821
        "IngestJob",
        back_populates="asset",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Asset(id={self.id}, title={self.title}, type={self.asset_type})>"

    @property
    def is_derivative(self) -> bool:
        return self.parent_id is not None

    @property
    def is_available(self) -> bool:
        return self.status == "available" and self.deleted_at is None
