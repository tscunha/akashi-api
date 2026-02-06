"""
AKASHI MAM API - Search Endpoints
Full-text search using PostgreSQL tsvector.
Multimodal search across transcriptions, faces, scenes, and metadata.
"""

import logging
import time
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, literal_column, select, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, OptionalUser, Pagination, get_tenant_by_code, get_db, get_tenant_id, get_current_user
from app.models import Asset, AssetKeyword
from app.models.user import User
from app.schemas import SearchResponse, SearchResult, SearchSuggestion
from app.schemas.search import (
    MultimodalSearchRequest,
    MultimodalSearchResponse,
    SearchSuggestion as SearchSuggestionSchema,
)
from app.services.search_service import search_service


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=SearchResponse)
async def search_assets(
    db: DbSession,
    pagination: Pagination,
    current_user: OptionalUser,
    q: str = Query(..., min_length=2, description="Search query"),
    asset_type: str | None = Query(None, description="Filter by asset type"),
    status: str | None = Query(None, description="Filter by status"),
    date_from: datetime | None = Query(None, description="Created after"),
    date_to: datetime | None = Query(None, description="Created before"),
    tenant_code: str | None = Query(None),
):
    """
    Full-text search across assets.

    Uses PostgreSQL tsvector for efficient search with ranking.
    Searches in: title (weight A), description (weight B), code (weight C).
    """
    start_time = time.time()

    tenant = await get_tenant_by_code(db, tenant_code)

    # Build search query with ts_query
    # Convert query to tsquery format
    search_terms = " & ".join(q.split())

    # Build the main query
    query = (
        select(
            Asset.id,
            Asset.title,
            Asset.description,
            Asset.asset_type,
            Asset.status,
            Asset.duration_ms,
            Asset.file_size_bytes,
            Asset.created_at,
            # Search rank
            func.ts_rank(
                Asset.search_vector,
                func.plainto_tsquery("portuguese", q)
            ).label("rank"),
            # Headline (highlighted snippet)
            func.ts_headline(
                "portuguese",
                func.coalesce(Asset.title, "") + " " + func.coalesce(Asset.description, ""),
                func.plainto_tsquery("portuguese", q),
                "StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15"
            ).label("headline"),
        )
        .where(
            Asset.tenant_id == tenant.id,
            Asset.deleted_at.is_(None),
            Asset.search_vector.op("@@")(func.plainto_tsquery("portuguese", q)),
        )
    )

    # Apply filters
    if asset_type:
        query = query.where(Asset.asset_type == asset_type)

    if status:
        query = query.where(Asset.status == status)
    else:
        # Default: only available assets
        query = query.where(Asset.status == "available")

    if date_from:
        query = query.where(Asset.created_at >= date_from)

    if date_to:
        query = query.where(Asset.created_at <= date_to)

    # Count total
    count_subquery = query.subquery()
    count_result = await db.execute(
        select(func.count()).select_from(count_subquery)
    )
    total = count_result.scalar() or 0

    # Paginate and order by rank
    offset = (pagination.page - 1) * pagination.page_size
    query = query.order_by(text("rank DESC")).offset(offset).limit(pagination.page_size)

    result = await db.execute(query)
    rows = result.all()

    # Build response
    results = [
        SearchResult(
            id=row.id,
            title=row.title,
            description=row.description,
            asset_type=row.asset_type,
            status=row.status,
            duration_ms=row.duration_ms,
            file_size_bytes=row.file_size_bytes,
            thumbnail_url=None,  # TODO: Add thumbnail URL
            created_at=row.created_at,
            rank=float(row.rank) if row.rank else None,
            headline=row.headline,
        )
        for row in rows
    ]

    search_time_ms = int((time.time() - start_time) * 1000)

    logger.info(f"Search '{q}' returned {total} results in {search_time_ms}ms")

    return SearchResponse(
        query=q,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        results=results,
        search_time_ms=search_time_ms,
    )


@router.get("/suggestions", response_model=list[SearchSuggestion])
async def get_search_suggestions(
    db: DbSession,
    q: str = Query(..., min_length=2, description="Partial search query"),
    tenant_code: str | None = Query(None),
    limit: int = Query(10, le=20),
):
    """
    Get search suggestions/autocomplete based on partial query.
    Searches in asset titles and keywords.
    """
    tenant = await get_tenant_by_code(db, tenant_code)

    suggestions = []

    # Search in asset titles
    title_query = (
        select(Asset.title, func.count().label("count"))
        .where(
            Asset.tenant_id == tenant.id,
            Asset.deleted_at.is_(None),
            Asset.title.ilike(f"%{q}%"),
        )
        .group_by(Asset.title)
        .order_by(text("count DESC"))
        .limit(limit // 2)
    )

    title_result = await db.execute(title_query)
    for row in title_result.all():
        suggestions.append(
            SearchSuggestion(
                text=row.title,
                type="title",
                count=row.count,
            )
        )

    # Search in keywords
    keyword_query = (
        select(AssetKeyword.keyword, func.count().label("count"))
        .where(
            AssetKeyword.tenant_id == tenant.id,
            AssetKeyword.keyword.ilike(f"%{q}%"),
        )
        .group_by(AssetKeyword.keyword)
        .order_by(text("count DESC"))
        .limit(limit // 2)
    )

    keyword_result = await db.execute(keyword_query)
    for row in keyword_result.all():
        suggestions.append(
            SearchSuggestion(
                text=row.keyword,
                type="keyword",
                count=row.count,
            )
        )

    # Sort by count and limit
    suggestions.sort(key=lambda x: x.count or 0, reverse=True)
    return suggestions[:limit]


@router.get("/advanced", response_model=SearchResponse)
async def advanced_search(
    db: DbSession,
    pagination: Pagination,
    current_user: OptionalUser,
    # Text search
    q: str | None = Query(None, description="Full-text search query"),
    title: str | None = Query(None, description="Search in title only"),
    description: str | None = Query(None, description="Search in description only"),
    # Filters
    asset_type: str | None = Query(None),
    status: str | None = Query(None),
    visibility: str | None = Query(None),
    # Date filters
    created_after: datetime | None = Query(None),
    created_before: datetime | None = Query(None),
    recorded_after: datetime | None = Query(None),
    recorded_before: datetime | None = Query(None),
    # Media filters
    min_duration_ms: int | None = Query(None),
    max_duration_ms: int | None = Query(None),
    min_size_bytes: int | None = Query(None),
    max_size_bytes: int | None = Query(None),
    # Keywords
    keywords: str | None = Query(None, description="Comma-separated keywords"),
    # Sorting
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    tenant_code: str | None = Query(None),
):
    """
    Advanced search with multiple filters and sorting options.
    """
    start_time = time.time()

    tenant = await get_tenant_by_code(db, tenant_code)

    # Build base query
    query = select(
        Asset.id,
        Asset.title,
        Asset.description,
        Asset.asset_type,
        Asset.status,
        Asset.duration_ms,
        Asset.file_size_bytes,
        Asset.created_at,
    ).where(
        Asset.tenant_id == tenant.id,
        Asset.deleted_at.is_(None),
    )

    # Full-text search
    if q:
        query = query.where(
            Asset.search_vector.op("@@")(func.plainto_tsquery("portuguese", q))
        )

    # Title/description search (simple ILIKE)
    if title:
        query = query.where(Asset.title.ilike(f"%{title}%"))

    if description:
        query = query.where(Asset.description.ilike(f"%{description}%"))

    # Type and status filters
    if asset_type:
        query = query.where(Asset.asset_type == asset_type)

    if status:
        query = query.where(Asset.status == status)

    if visibility:
        query = query.where(Asset.visibility == visibility)

    # Date filters
    if created_after:
        query = query.where(Asset.created_at >= created_after)

    if created_before:
        query = query.where(Asset.created_at <= created_before)

    if recorded_after:
        query = query.where(Asset.recorded_at >= recorded_after)

    if recorded_before:
        query = query.where(Asset.recorded_at <= recorded_before)

    # Media filters
    if min_duration_ms is not None:
        query = query.where(Asset.duration_ms >= min_duration_ms)

    if max_duration_ms is not None:
        query = query.where(Asset.duration_ms <= max_duration_ms)

    if min_size_bytes is not None:
        query = query.where(Asset.file_size_bytes >= min_size_bytes)

    if max_size_bytes is not None:
        query = query.where(Asset.file_size_bytes <= max_size_bytes)

    # Keyword filter
    if keywords:
        keyword_list = [k.strip() for k in keywords.split(",")]
        # Subquery to find assets with matching keywords
        keyword_subquery = (
            select(AssetKeyword.asset_id)
            .where(AssetKeyword.keyword.in_(keyword_list))
            .distinct()
        )
        query = query.where(Asset.id.in_(keyword_subquery))

    # Count total
    count_subquery = query.subquery()
    count_result = await db.execute(
        select(func.count()).select_from(count_subquery)
    )
    total = count_result.scalar() or 0

    # Sorting
    sort_column = getattr(Asset, sort_by, Asset.created_at)
    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Paginate
    offset = (pagination.page - 1) * pagination.page_size
    query = query.offset(offset).limit(pagination.page_size)

    result = await db.execute(query)
    rows = result.all()

    results = [
        SearchResult(
            id=row.id,
            title=row.title,
            description=row.description,
            asset_type=row.asset_type,
            status=row.status,
            duration_ms=row.duration_ms,
            file_size_bytes=row.file_size_bytes,
            thumbnail_url=None,
            created_at=row.created_at,
        )
        for row in rows
    ]

    search_time_ms = int((time.time() - start_time) * 1000)

    return SearchResponse(
        query=q or "",
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        results=results,
        search_time_ms=search_time_ms,
    )


# ======================
# Multimodal Search
# ======================


@router.post("/multimodal", response_model=MultimodalSearchResponse)
async def multimodal_search(
    request: MultimodalSearchRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
    current_user: User = Depends(get_current_user),
):
    """
    Multimodal search across all data sources.

    Searches in:
    - Transcriptions (speech-to-text)
    - Scene descriptions (vision AI)
    - Faces (similarity matching with uploaded image)
    - Keywords (manual and AI-extracted)
    - Metadata (title, description)

    Results are ranked using Reciprocal Rank Fusion (RRF) to combine
    scores from different sources.
    """
    return await search_service.search(db, request, tenant_id)


@router.get("/multimodal/suggestions", response_model=list[SearchSuggestionSchema])
async def get_multimodal_suggestions(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Get search suggestions for multimodal search.

    Suggests keywords, person names, and collection names.
    """
    return await search_service.get_suggestions(db, q, tenant_id, limit)
