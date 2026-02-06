"""
AKASHI MAM API - Assets Endpoints
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, Pagination, get_tenant_by_code
from app.models import Asset, Tenant
from app.models.asset_storage import AssetStorageLocation
from app.schemas import (
    AssetCreate,
    AssetUpdate,
    AssetRead,
    AssetSummary,
    AssetListResponse,
    MessageResponse,
)
from app.services.storage_service import StorageService

# Initialize storage service for URL generation
storage_service = StorageService()


router = APIRouter()


@router.get("", response_model=AssetListResponse)
async def list_assets(
    db: DbSession,
    pagination: Pagination,
    tenant_code: str | None = Query(None, description="Filter by tenant code"),
    asset_type: str | None = Query(None, description="Filter by asset type"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    search: str | None = Query(None, description="Search in title"),
):
    """
    List assets with pagination and filters.
    """
    # Build base query
    query = select(Asset).where(Asset.deleted_at.is_(None))

    # Apply filters
    if tenant_code:
        tenant = await get_tenant_by_code(db, tenant_code)
        query = query.where(Asset.tenant_id == tenant.id)

    if asset_type:
        query = query.where(Asset.asset_type == asset_type)

    if status_filter:
        query = query.where(Asset.status == status_filter)

    if search:
        query = query.where(Asset.title.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Apply pagination and ordering
    query = (
        query.order_by(Asset.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    # Execute query
    result = await db.execute(query)
    assets = result.scalars().all()

    # Get asset IDs for thumbnail lookup
    asset_ids = [asset.id for asset in assets]

    # Fetch thumbnail storage locations
    thumbnail_query = (
        select(AssetStorageLocation)
        .where(
            AssetStorageLocation.asset_id.in_(asset_ids),
            AssetStorageLocation.purpose == "thumbnail",
            AssetStorageLocation.is_accessible == True,
        )
    )
    thumbnail_result = await db.execute(thumbnail_query)
    thumbnails = {loc.asset_id: loc for loc in thumbnail_result.scalars().all()}

    # Map to summary with thumbnail URLs
    items = []
    for asset in assets:
        thumbnail_url = None
        if asset.id in thumbnails:
            thumb = thumbnails[asset.id]
            if thumb.bucket and thumb.path:
                try:
                    thumbnail_url = await storage_service.get_presigned_url(
                        thumb.bucket, thumb.path, expires_in=3600
                    )
                except Exception:
                    pass  # Skip if URL generation fails

        items.append(
            AssetSummary(
                id=asset.id,
                title=asset.title,
                asset_type=asset.asset_type,
                status=asset.status,
                duration_ms=asset.duration_ms,
                file_size_bytes=asset.file_size_bytes,
                thumbnail_url=thumbnail_url,
                created_at=asset.created_at,
            )
        )

    pages = (total + pagination.page_size - 1) // pagination.page_size if pagination.page_size > 0 else 0

    return AssetListResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=pages,
    )


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(
    asset_id: UUID,
    db: DbSession,
):
    """
    Get a single asset by ID.
    """
    query = (
        select(Asset)
        .where(Asset.id == asset_id, Asset.deleted_at.is_(None))
        .options(
            selectinload(Asset.storage_locations),
            selectinload(Asset.technical_metadata),
        )
    )

    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    return asset


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(
    data: AssetCreate,
    db: DbSession,
):
    """
    Create a new asset (metadata only, without file).
    Use POST /ingest to create asset with file upload.
    """
    # Get tenant
    tenant = await get_tenant_by_code(db, data.tenant_code)

    # Create asset
    asset = Asset(
        tenant_id=tenant.id,
        title=data.title,
        description=data.description,
        asset_type=data.asset_type,
        code=data.code,
        slug=data.slug,
        duration_ms=data.duration_ms,
        recorded_at=data.recorded_at,
        content_rating=data.content_rating,
        visibility=data.visibility,
        external_ids=data.external_ids,
        parent_id=data.parent_id,
        extra=data.extra,
        status="ingesting",
    )

    db.add(asset)
    await db.flush()
    await db.refresh(asset)

    return asset


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(
    asset_id: UUID,
    data: AssetUpdate,
    db: DbSession,
):
    """
    Update an existing asset.
    """
    # Get asset
    query = select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asset, field, value)

    await db.flush()
    await db.refresh(asset)

    return asset


@router.delete("/{asset_id}", response_model=MessageResponse)
async def delete_asset(
    asset_id: UUID,
    db: DbSession,
    hard_delete: bool = Query(False, description="Permanently delete the asset"),
):
    """
    Delete an asset (soft delete by default).
    """
    # Get asset
    query = select(Asset).where(Asset.id == asset_id)
    if not hard_delete:
        query = query.where(Asset.deleted_at.is_(None))

    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    if hard_delete:
        # TODO: Delete from storage as well
        await db.delete(asset)
        message = f"Asset {asset_id} permanently deleted"
    else:
        # Soft delete
        asset.deleted_at = datetime.utcnow()
        asset.status = "deleted"
        message = f"Asset {asset_id} moved to trash"

    return MessageResponse(message=message, id=asset_id)
