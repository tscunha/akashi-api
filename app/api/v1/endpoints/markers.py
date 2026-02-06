"""
AKASHI MAM API - Markers Endpoints
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.models import Asset, AssetMarker
from app.schemas import (
    MarkerCreate,
    MarkerUpdate,
    MarkerRead,
    MarkerListResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Asset Markers Routes
# =============================================================================


@router.get("/assets/{asset_id}/markers", response_model=MarkerListResponse)
async def list_asset_markers(
    asset_id: UUID,
    db: DbSession,
    marker_type: str | None = Query(None, description="Filter by marker type"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List all markers for a specific asset.
    Ordered by start time.
    """
    # Verify asset exists
    asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Build query
    query = (
        select(AssetMarker)
        .where(AssetMarker.asset_id == asset_id)
    )

    if marker_type:
        query = query.where(AssetMarker.marker_type == marker_type)

    query = query.order_by(AssetMarker.start_ms).limit(limit).offset(offset)

    result = await db.execute(query)
    markers = list(result.scalars().all())

    # Count total
    count_query = select(func.count()).where(AssetMarker.asset_id == asset_id)
    if marker_type:
        count_query = count_query.where(AssetMarker.marker_type == marker_type)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return MarkerListResponse(
        items=[MarkerRead.model_validate(m) for m in markers],
        total=total,
    )


@router.post("/assets/{asset_id}/markers", response_model=MarkerRead, status_code=201)
async def create_marker(
    asset_id: UUID,
    data: MarkerCreate,
    db: DbSession,
):
    """
    Create a new marker on an asset.
    """
    # Verify asset exists
    asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Validate start_ms against asset duration
    if asset.duration_ms and data.start_ms > asset.duration_ms:
        raise HTTPException(
            status_code=400,
            detail=f"start_ms ({data.start_ms}) exceeds asset duration ({asset.duration_ms}ms)",
        )

    # Create marker
    marker = AssetMarker(
        asset_id=asset_id,
        tenant_id=asset.tenant_id,
        marker_type=data.marker_type,
        name=data.name,
        color=data.color,
        start_ms=data.start_ms,
        duration_ms=data.duration_ms,
        note=data.note,
        keywords=data.keywords,
        source=data.source,
        extra=data.extra,
    )
    db.add(marker)
    await db.flush()
    await db.refresh(marker)

    logger.info(f"Marker '{data.marker_type}' created at {data.start_ms}ms on asset {asset_id}")
    return MarkerRead.model_validate(marker)


# =============================================================================
# Individual Marker Routes
# =============================================================================


@router.get("/markers/{marker_id}", response_model=MarkerRead)
async def get_marker(
    marker_id: UUID,
    db: DbSession,
):
    """
    Get a specific marker by ID.
    """
    result = await db.execute(
        select(AssetMarker).where(AssetMarker.id == marker_id)
    )
    marker = result.scalar_one_or_none()

    if not marker:
        raise HTTPException(status_code=404, detail="Marker not found")

    return MarkerRead.model_validate(marker)


@router.patch("/markers/{marker_id}", response_model=MarkerRead)
async def update_marker(
    marker_id: UUID,
    data: MarkerUpdate,
    db: DbSession,
):
    """
    Update a marker.
    """
    result = await db.execute(
        select(AssetMarker).where(AssetMarker.id == marker_id)
    )
    marker = result.scalar_one_or_none()

    if not marker:
        raise HTTPException(status_code=404, detail="Marker not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(marker, field, value)

    await db.flush()
    await db.refresh(marker)

    logger.info(f"Marker {marker_id} updated")
    return MarkerRead.model_validate(marker)


@router.delete("/markers/{marker_id}", response_model=MessageResponse)
async def delete_marker(
    marker_id: UUID,
    db: DbSession,
):
    """
    Delete a marker.
    """
    result = await db.execute(
        select(AssetMarker).where(AssetMarker.id == marker_id)
    )
    marker = result.scalar_one_or_none()

    if not marker:
        raise HTTPException(status_code=404, detail="Marker not found")

    await db.delete(marker)
    await db.flush()

    logger.info(f"Marker {marker_id} deleted")
    return MessageResponse(message="Marker deleted", id=marker_id)
