"""
AKASHI MAM API - Asset Storage Location Model
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ExtraMixin


StorageType = Literal["s3", "lto", "glacier", "local", "external_url"]
StorageTier = Literal["hot", "warm", "cold", "archive"]
StoragePurpose = Literal["original", "proxy", "thumbnail", "sprite", "hls", "dash"]
VerificationStatus = Literal["ok", "mismatch", "missing", "pending"]


class AssetStorageLocation(Base, ExtraMixin):
    """
    Model representing physical locations of asset files.
    An asset can have multiple storage locations (original, proxies, thumbnails).
    """

    __tablename__ = "asset_storage_locations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
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

    # Location
    storage_type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_tier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Integrity
    checksum_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        server_default="pending",
    )

    # Status
    is_primary: Mapped[bool] = mapped_column(default=False, server_default="false")
    is_accessible: Mapped[bool] = mapped_column(default=True, server_default="true")
    status: Mapped[str] = mapped_column(
        String(50),
        default="available",
        server_default="available",
    )

    # Purpose (what this file is for)
    purpose: Mapped[str] = mapped_column(
        String(50),
        default="original",
        server_default="original",
    )

    # LTO specific
    lto_tape_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lto_position: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        server_default="NOW()",
        nullable=False,
    )
    migrated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    asset: Mapped["Asset"] = relationship(  # noqa: F821
        "Asset",
        back_populates="storage_locations",
    )

    def __repr__(self) -> str:
        return f"<AssetStorageLocation(asset_id={self.asset_id}, purpose={self.purpose}, bucket={self.bucket})>"

    @property
    def full_path(self) -> str:
        """Return the full S3-style path."""
        if self.bucket and self.path:
            return f"s3://{self.bucket}/{self.path}"
        return self.url or ""


class AssetTechnicalMetadata(Base):
    """
    Model for technical/codec metadata.
    Critical for broadcast workflows.
    """

    __tablename__ = "asset_technical_metadata"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )

    # Video properties
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    frame_rate: Mapped[float | None] = mapped_column(nullable=True)
    frame_rate_num: Mapped[int | None] = mapped_column(nullable=True)
    frame_rate_den: Mapped[int | None] = mapped_column(nullable=True)
    scan_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    aspect_ratio: Mapped[str | None] = mapped_column(String(20), nullable=True)
    color_space: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bit_depth: Mapped[int | None] = mapped_column(nullable=True)
    hdr_format: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Video codec
    video_codec: Mapped[str | None] = mapped_column(String(100), nullable=True)
    video_codec_profile: Mapped[str | None] = mapped_column(String(100), nullable=True)
    video_bitrate_bps: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Audio properties
    audio_codec: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_sample_rate: Mapped[int | None] = mapped_column(nullable=True)
    audio_bit_depth: Mapped[int | None] = mapped_column(nullable=True)
    audio_channels: Mapped[int | None] = mapped_column(nullable=True)
    audio_channel_layout: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_bitrate_bps: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Container
    container_format: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timecode
    start_timecode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    drop_frame: Mapped[bool] = mapped_column(default=False, server_default="false")

    # Computed
    resolution_category: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Raw output
    mediainfo_raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )
    ffprobe_raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )

    # Analysis
    analyzed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    analyzer_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        server_default="NOW()",
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default="NOW()",
        nullable=False,
    )

    # Relationships
    asset: Mapped["Asset"] = relationship(  # noqa: F821
        "Asset",
        back_populates="technical_metadata",
    )

    def __repr__(self) -> str:
        return f"<AssetTechnicalMetadata(asset_id={self.asset_id}, {self.width}x{self.height})>"


class IngestJob(Base):
    """
    Model for tracking processing jobs.
    """

    __tablename__ = "ingest_jobs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
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

    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        server_default="pending",
    )
    priority: Mapped[int] = mapped_column(default=5, server_default="5")

    input_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    progress: Mapped[int] = mapped_column(default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(nullable=True)

    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default="NOW()",
        nullable=False,
    )

    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )

    # Relationships
    asset: Mapped["Asset"] = relationship(  # noqa: F821
        "Asset",
        back_populates="ingest_jobs",
    )

    def __repr__(self) -> str:
        return f"<IngestJob(id={self.id}, type={self.job_type}, status={self.status})>"
