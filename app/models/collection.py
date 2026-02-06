"""
AKASHI MAM API - Collection Models
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.tenant import Tenant
    from app.models.user import User


CollectionType = Literal["manual", "smart", "system"]


class Collection(Base):
    """Collection model for grouping assets."""

    __tablename__ = "collections"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)

    collection_type: Mapped[str] = mapped_column(
        String(50),
        default="manual",
        nullable=False,
    )

    # Smart collection filter (JSON query)
    filter_query: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Display settings
    cover_asset_id: Mapped[UUID | None] = mapped_column(nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Denormalized count for performance
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="joined")
    creator: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="joined",
    )
    items: Mapped[list["CollectionItem"]] = relationship(
        "CollectionItem",
        back_populates="collection",
        lazy="selectin",
        order_by="CollectionItem.position",
    )

    def __repr__(self) -> str:
        return f"<Collection {self.name}>"


class CollectionItem(Base):
    """Collection item linking assets to collections."""

    __tablename__ = "collection_items"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
    )

    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    added_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    collection: Mapped["Collection"] = relationship(
        "Collection",
        back_populates="items",
    )

    def __repr__(self) -> str:
        return f"<CollectionItem collection={self.collection_id} asset={self.asset_id}>"
