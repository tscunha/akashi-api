"""
AKASHI MAM API - Keywords Endpoints
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DbSession, get_tenant_by_code
from app.models import Asset, AssetKeyword
from app.schemas import (
    KeywordCreate,
    KeywordUpdate,
    KeywordRead,
    KeywordListResponse,
    KeywordSearchResult,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Asset Keywords Routes
# =============================================================================


@router.get("/assets/{asset_id}/keywords", response_model=KeywordListResponse)
async def list_asset_keywords(
    asset_id: UUID,
    db: DbSession,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List all keywords for a specific asset.
    """
    # Verify asset exists
    asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Get keywords
    query = (
        select(AssetKeyword)
        .where(AssetKeyword.asset_id == asset_id)
        .order_by(AssetKeyword.start_ms.nulls_last(), AssetKeyword.keyword)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    keywords = list(result.scalars().all())

    # Count total
    count_result = await db.execute(
        select(func.count()).where(AssetKeyword.asset_id == asset_id)
    )
    total = count_result.scalar() or 0

    return KeywordListResponse(
        items=[KeywordRead.model_validate(k) for k in keywords],
        total=total,
    )


@router.post("/assets/{asset_id}/keywords", response_model=KeywordRead, status_code=201)
async def create_keyword(
    asset_id: UUID,
    data: KeywordCreate,
    db: DbSession,
):
    """
    Add a keyword to an asset.
    """
    # Verify asset exists
    asset_result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Check for duplicate
    existing = await db.execute(
        select(AssetKeyword).where(
            AssetKeyword.asset_id == asset_id,
            AssetKeyword.keyword == data.keyword,
            AssetKeyword.start_ms == data.start_ms,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Keyword already exists at this time position",
        )

    # Create keyword
    keyword = AssetKeyword(
        asset_id=asset_id,
        tenant_id=asset.tenant_id,
        keyword=data.keyword,
        start_ms=data.start_ms,
        end_ms=data.end_ms,
        note=data.note,
        source=data.source,
        confidence=data.confidence,
    )
    db.add(keyword)
    await db.flush()
    await db.refresh(keyword)

    logger.info(f"Keyword '{data.keyword}' added to asset {asset_id}")
    return KeywordRead.model_validate(keyword)


# =============================================================================
# Search Routes (MUST come before /keywords/{keyword_id} to avoid path conflict)
# =============================================================================


@router.get("/keywords/search", response_model=list[KeywordSearchResult])
async def search_keywords(
    db: DbSession,
    q: str = Query(..., min_length=2, description="Search term"),
    tenant_code: str | None = Query(None),
    limit: int = Query(50, le=200),
):
    """
    Search keywords across all assets.
    Returns keywords matching the search term with asset information.
    """
    # Get tenant if specified
    tenant_id = None
    if tenant_code:
        tenant = await get_tenant_by_code(db, tenant_code)
        tenant_id = tenant.id

    # Build search query using ILIKE (simple search)
    # Note: The table has a GIN trigram index for more advanced search
    query = (
        select(
            AssetKeyword.id,
            AssetKeyword.asset_id,
            AssetKeyword.keyword,
            AssetKeyword.start_ms,
            AssetKeyword.end_ms,
            Asset.title.label("asset_title"),
            Asset.asset_type.label("asset_type"),
        )
        .join(Asset, Asset.id == AssetKeyword.asset_id)
        .where(AssetKeyword.keyword.ilike(f"%{q}%"))
    )

    if tenant_id:
        query = query.where(AssetKeyword.tenant_id == tenant_id)

    query = query.order_by(AssetKeyword.keyword).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return [
        KeywordSearchResult(
            id=row.id,
            asset_id=row.asset_id,
            keyword=row.keyword,
            start_ms=row.start_ms,
            end_ms=row.end_ms,
            asset_title=row.asset_title,
            asset_type=row.asset_type,
        )
        for row in rows
    ]


# =============================================================================
# Individual Keyword Routes
# =============================================================================


@router.get("/keywords/{keyword_id}", response_model=KeywordRead)
async def get_keyword(
    keyword_id: UUID,
    db: DbSession,
):
    """
    Get a specific keyword by ID.
    """
    result = await db.execute(
        select(AssetKeyword).where(AssetKeyword.id == keyword_id)
    )
    keyword = result.scalar_one_or_none()

    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    return KeywordRead.model_validate(keyword)


@router.patch("/keywords/{keyword_id}", response_model=KeywordRead)
async def update_keyword(
    keyword_id: UUID,
    data: KeywordUpdate,
    db: DbSession,
):
    """
    Update a keyword.
    """
    result = await db.execute(
        select(AssetKeyword).where(AssetKeyword.id == keyword_id)
    )
    keyword = result.scalar_one_or_none()

    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(keyword, field, value)

    await db.flush()
    await db.refresh(keyword)

    logger.info(f"Keyword {keyword_id} updated")
    return KeywordRead.model_validate(keyword)


@router.delete("/keywords/{keyword_id}", response_model=MessageResponse)
async def delete_keyword(
    keyword_id: UUID,
    db: DbSession,
):
    """
    Delete a keyword.
    """
    result = await db.execute(
        select(AssetKeyword).where(AssetKeyword.id == keyword_id)
    )
    keyword = result.scalar_one_or_none()

    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    await db.delete(keyword)
    await db.flush()

    logger.info(f"Keyword {keyword_id} deleted")
    return MessageResponse(message="Keyword deleted", id=keyword_id)
