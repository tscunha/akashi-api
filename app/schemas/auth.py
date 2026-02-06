"""
AKASHI MAM API - Authentication Schemas
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import BaseSchema


UserRole = Literal["admin", "manager", "editor", "viewer", "user"]


# =============================================================================
# Token Schemas
# =============================================================================


class Token(BaseSchema):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token expiration time in seconds")


class TokenPair(BaseSchema):
    """JWT token pair with refresh token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token expiration time in seconds")
    refresh_expires_in: int = Field(description="Refresh token expiration time in seconds")


class TokenPayload(BaseSchema):
    """JWT token payload (internal use)."""

    sub: str  # user_id
    tenant_id: str
    role: str
    exp: int  # expiration timestamp


class RefreshTokenRequest(BaseSchema):
    """Request to refresh access token."""

    refresh_token: str = Field(..., description="The refresh token")


# =============================================================================
# Login Schemas
# =============================================================================


class LoginRequest(BaseSchema):
    """Login request with email and password."""

    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginResponse(BaseSchema):
    """Login response with token and user info."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int | None = None
    user: "UserRead"


class LoginResponseV2(BaseSchema):
    """Login response with token pair and user info (v2)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
    user: "UserRead"


# =============================================================================
# User Schemas
# =============================================================================


class UserCreate(BaseSchema):
    """Schema for creating a user."""

    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: str | None = Field(None, max_length=255)
    role: UserRole = "user"
    tenant_code: str | None = Field(None, description="Tenant code (uses 'dev' if not provided)")


class UserUpdate(BaseSchema):
    """Schema for updating a user."""

    email: EmailStr | None = None
    full_name: str | None = Field(None, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class UserRead(BaseSchema):
    """Schema for reading a user."""

    id: UUID
    tenant_id: UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserSummary(BaseSchema):
    """Minimal user summary."""

    id: UUID
    email: str
    full_name: str | None
    role: str


class PasswordChange(BaseSchema):
    """Password change request."""

    current_password: str
    new_password: str = Field(..., min_length=8)


# Forward reference update
LoginResponse.model_rebuild()
LoginResponseV2.model_rebuild()
