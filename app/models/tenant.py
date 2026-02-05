"""
AKASHI MAM API - Tenant Model
"""

from typing import Any
from uuid import UUID

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    """
    Tenant model representing organizations/clients.
    All data in the system is scoped to a tenant.
    """

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )
    metadata_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        server_default="true",
    )

    # Relationships
    assets: Mapped[list["Asset"]] = relationship(  # noqa: F821
        "Asset",
        back_populates="tenant",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Tenant(code={self.code}, name={self.name})>"
