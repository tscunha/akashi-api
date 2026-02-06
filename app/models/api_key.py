"""API Key model for external integrations and MCP server."""

import hashlib
import secrets
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class APIKey(Base):
    """Model for storing API keys for external access."""

    __tablename__ = "api_keys"

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
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Key info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(10), nullable=False)  # ak_xxxx

    # Permissions
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=lambda: ["read"]
    )  # read, write, admin

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"

    @staticmethod
    def generate_key() -> tuple[str, str, str]:
        """
        Generate a new API key.

        Returns:
            tuple: (full_key, key_hash, key_prefix)
        """
        # Generate random key
        random_part = secrets.token_urlsafe(32)
        full_key = f"ak_{random_part}"

        # Hash for storage
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()

        # Prefix for identification (first 8 chars after ak_)
        key_prefix = f"ak_{random_part[:4]}"

        return full_key, key_hash, key_prefix

    @staticmethod
    def hash_key(key: str) -> str:
        """Hash an API key for lookup."""
        return hashlib.sha256(key.encode()).hexdigest()

    def has_scope(self, scope: str) -> bool:
        """Check if this key has a specific scope."""
        if "admin" in self.scopes:
            return True
        return scope in self.scopes

    def is_valid(self) -> bool:
        """Check if the key is valid (active and not expired)."""
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < datetime.now(self.expires_at.tzinfo):
            return False
        return True
