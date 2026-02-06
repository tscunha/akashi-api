"""
API Keys management endpoints.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_tenant_id
from app.models.api_key import APIKey
from app.models.user import User

router = APIRouter()


# ===================
# Schemas
# ===================


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""

    name: str = Field(..., max_length=255)
    scopes: list[str] = Field(default=["read"])
    expires_in_days: int | None = Field(None, ge=1, le=365)


class APIKeyRead(BaseModel):
    """Schema for reading an API key (without the actual key)."""

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreated(BaseModel):
    """Response when creating an API key (includes the full key)."""

    id: UUID
    name: str
    key: str  # Full key, only shown once!
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    created_at: datetime


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key."""

    name: str | None = Field(None, max_length=255)
    scopes: list[str] | None = None
    is_active: bool | None = None


# ===================
# Endpoints
# ===================


@router.get("/api-keys", response_model=list[APIKeyRead])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """List all API keys for the current user."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == current_user.id)
        .where(APIKey.tenant_id == tenant_id)
        .order_by(APIKey.created_at.desc())
    )
    return result.scalars().all()


@router.post("/api-keys", response_model=APIKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_in: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new API key.

    **Important**: The full key is only returned once. Store it securely!
    """
    from datetime import timedelta

    # Generate the key
    full_key, key_hash, key_prefix = APIKey.generate_key()

    # Calculate expiration
    expires_at = None
    if key_in.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=key_in.expires_in_days)

    # Validate scopes
    valid_scopes = {"read", "write", "admin"}
    for scope in key_in.scopes:
        if scope not in valid_scopes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope: {scope}. Valid scopes: {valid_scopes}",
            )

    # Create the key
    api_key = APIKey(
        tenant_id=tenant_id,
        user_id=current_user.id,
        name=key_in.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=key_in.scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return APIKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key=full_key,  # Only time we return the full key!
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.get("/api-keys/{key_id}", response_model=APIKeyRead)
async def get_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Get an API key by ID."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == key_id)
        .where(APIKey.user_id == current_user.id)
        .where(APIKey.tenant_id == tenant_id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return api_key


@router.patch("/api-keys/{key_id}", response_model=APIKeyRead)
async def update_api_key(
    key_id: UUID,
    key_in: APIKeyUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Update an API key."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == key_id)
        .where(APIKey.user_id == current_user.id)
        .where(APIKey.tenant_id == tenant_id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    update_data = key_in.model_dump(exclude_unset=True)

    # Validate scopes if provided
    if "scopes" in update_data:
        valid_scopes = {"read", "write", "admin"}
        for scope in update_data["scopes"]:
            if scope not in valid_scopes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid scope: {scope}",
                )

    for field, value in update_data.items():
        setattr(api_key, field, value)

    await db.commit()
    await db.refresh(api_key)

    return api_key


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Delete an API key."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == key_id)
        .where(APIKey.user_id == current_user.id)
        .where(APIKey.tenant_id == tenant_id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    await db.delete(api_key)
    await db.commit()


@router.post("/api-keys/{key_id}/revoke", response_model=APIKeyRead)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """Revoke an API key (set inactive)."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == key_id)
        .where(APIKey.user_id == current_user.id)
        .where(APIKey.tenant_id == tenant_id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    api_key.is_active = False
    await db.commit()
    await db.refresh(api_key)

    return api_key
