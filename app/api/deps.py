"""
AKASHI MAM API - Dependencies
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Tenant
from app.schemas import PaginationParams


# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]


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
