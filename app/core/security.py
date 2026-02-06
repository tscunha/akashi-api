"""
AKASHI MAM API - Security Utilities
JWT token handling, password hashing, and refresh tokens.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


# =============================================================================
# Password Functions
# =============================================================================


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: The plain text password to verify
        hashed_password: The hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    password_bytes = plain_password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: The plain text password to hash

    Returns:
        The hashed password string

    Note:
        bcrypt has a 72-byte limit. Passwords are truncated if necessary.
    """
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


# =============================================================================
# JWT Token Functions
# =============================================================================


def create_access_token(
    subject: str,
    tenant_id: str,
    role: str = "user",
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        subject: The subject of the token (typically user_id)
        tenant_id: The tenant ID for multi-tenancy
        role: The user's role
        expires_delta: Optional custom expiration time
        extra_claims: Optional additional claims to include

    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )

    to_encode = {
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    Decode and validate a JWT access token.

    Args:
        token: The JWT token string to decode

    Returns:
        The decoded token payload, or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        # Verify token type if present
        if payload.get("type") and payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def get_token_expiration_seconds() -> int:
    """
    Get the token expiration time in seconds.

    Returns:
        Number of seconds until token expiration
    """
    return settings.jwt_access_token_expire_minutes * 60


# =============================================================================
# Refresh Token Functions
# =============================================================================


def generate_refresh_token() -> str:
    """
    Generate a secure random refresh token.

    Returns:
        A secure random token string (64 characters)
    """
    return secrets.token_urlsafe(48)  # 64 chars base64


def hash_refresh_token(token: str) -> str:
    """
    Hash a refresh token for storage.

    Args:
        token: The plain refresh token

    Returns:
        SHA-256 hash of the token
    """
    return hashlib.sha256(token.encode()).hexdigest()


def get_refresh_token_expiration() -> datetime:
    """
    Get the expiration datetime for a new refresh token.

    Returns:
        Expiration datetime
    """
    return datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )


def get_refresh_token_expiration_seconds() -> int:
    """
    Get the refresh token expiration time in seconds.

    Returns:
        Number of seconds until refresh token expiration
    """
    return settings.jwt_refresh_token_expire_days * 24 * 60 * 60


# =============================================================================
# Token Pair Functions
# =============================================================================


def create_token_pair(
    user_id: str,
    tenant_id: str,
    role: str = "user",
) -> dict[str, Any]:
    """
    Create both access and refresh tokens.

    Args:
        user_id: The user ID
        tenant_id: The tenant ID
        role: The user's role

    Returns:
        Dictionary containing access_token, refresh_token, and expiration info
    """
    access_token = create_access_token(
        subject=user_id,
        tenant_id=tenant_id,
        role=role,
    )

    refresh_token = generate_refresh_token()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "refresh_token_hash": hash_refresh_token(refresh_token),
        "token_type": "bearer",
        "expires_in": get_token_expiration_seconds(),
        "refresh_expires_in": get_refresh_token_expiration_seconds(),
    }
