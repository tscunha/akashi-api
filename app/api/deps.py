"""
AKASHI MAM API - Dependencies
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as _get_db
from app.core.security import decode_access_token
from app.models import Tenant, User
from app.schemas import PaginationParams


# Re-export get_db for convenience
get_db = _get_db


# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(_get_db)]


async def get_tenant_by_code(
    db: DbSession,
    tenant_code: str | None = None,
) -> Tenant:
    """Get tenant by code, defaulting to 'dev' if not specified."""
    code = tenant_code or "dev"
    result = await db.execute(
        select(Tenant).where(Tenant.code == code, Tenant.is_active == True)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{code}' not found or inactive",
        )

    return tenant


async def get_pagination(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginationParams:
    """Get pagination parameters from query string."""
    return PaginationParams(page=page, page_size=page_size)


# Type aliases
Pagination = Annotated[PaginationParams, Depends(get_pagination)]


# =============================================================================
# Authentication Dependencies
# =============================================================================


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    """
    Get the current authenticated user from JWT token.

    Raises HTTPException 401 if token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise credentials_exception

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # Get user from database
    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: "User" = Depends(get_current_user),
) -> User:
    """
    Get the current authenticated user, ensuring they are active.

    Raises HTTPException 403 if user is inactive.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get the current user, ensuring they are a superuser.

    Raises HTTPException 403 if user is not a superuser.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return current_user


async def get_optional_current_user(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User | None:
    """
    Get the current user if authenticated, or None if not.

    Useful for endpoints that work with or without authentication.
    """
    if not credentials:
        return None

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    return result.scalar_one_or_none()


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]
OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]


async def get_tenant_id(
    current_user: User = Depends(get_current_user),
) -> UUID:
    """
    Get the tenant ID from the current authenticated user.

    Returns the tenant_id of the authenticated user.
    """
    return current_user.tenant_id


# Type alias for tenant ID
TenantId = Annotated[UUID, Depends(get_tenant_id)]
