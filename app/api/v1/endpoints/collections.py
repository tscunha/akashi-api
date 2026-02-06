"""
AKASHI MAM API - Collections Endpoints
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import (
    CurrentActiveUser,
    DbSession,
    OptionalUser,
    Pagination,
    get_tenant_by_code,
)
from app.models import Asset, Collection, CollectionItem
from app.schemas import (
    BulkAddItemsRequest,
    CollectionCreate,
    CollectionItemCreate,
    CollectionItemRead,
    CollectionItemUpdate,
    CollectionItemWithAsset,
    CollectionListResponse,
    CollectionRead,
    CollectionSummary,
    CollectionUpdate,
    CollectionWithItems,
    MessageResponse,
    ReorderItemsRequest,
)


logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Collection CRUD Endpoints
# =============================================================================


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    db: DbSession,
    pagination: Pagination,
    current_user: OptionalUser,
    tenant_code: str | None = Query(None),
    collection_type: str | None = Query(None),
    include_public: bool = Query(True, description="Include public collections"),
):
    """
    List collections.
    - Authenticated users see their own + public collections
    - Unauthenticated users see only public collections
    """
    # Get tenant
    tenant = await get_tenant_by_code(db, tenant_code)

    # Build query
    query = select(Collection).where(Collection.tenant_id == tenant.id)

    # Filter by visibility
    if current_user:
        if include_public:
            query = query.where(
                (Collection.created_by == current_user.id) | (Collection.is_public == True)
            )
        else:
            query = query.where(Collection.created_by == current_user.id)
    else:
        query = query.where(Collection.is_public == True)

    if collection_type:
        query = query.where(Collection.collection_type == collection_type)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    offset = (pagination.page - 1) * pagination.page_size
    query = query.order_by(Collection.updated_at.desc()).offset(offset).limit(pagination.page_size)

    result = await db.execute(query)
    collections = list(result.scalars().all())

    return CollectionListResponse(
        items=[CollectionSummary.model_validate(c) for c in collections],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=CollectionRead, status_code=201)
async def create_collection(
    data: CollectionCreate,
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Create a new collection.
    """
    tenant = await get_tenant_by_code(db, data.tenant_code)

    # Check for duplicate slug
    if data.slug:
        existing = await db.execute(
            select(Collection).where(
                Collection.tenant_id == tenant.id,
                Collection.slug == data.slug,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Collection with this slug already exists",
            )

    collection = Collection(
        tenant_id=tenant.id,
        name=data.name,
        description=data.description,
        slug=data.slug,
        collection_type=data.collection_type,
        filter_query=data.filter_query,
        color=data.color,
        icon=data.icon,
        is_public=data.is_public,
        created_by=current_user.id,
    )

    db.add(collection)
    await db.flush()
    await db.refresh(collection)

    logger.info(f"Collection '{collection.name}' created by user {current_user.id}")
    return CollectionRead.model_validate(collection)


@router.get("/{collection_id}", response_model=CollectionWithItems)
async def get_collection(
    collection_id: UUID,
    db: DbSession,
    current_user: OptionalUser,
):
    """
    Get a collection with its items.
    """
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Check access
    if not collection.is_public:
        if not current_user or collection.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")

    # Get items with asset info
    items_query = (
        select(
            CollectionItem.id,
            CollectionItem.asset_id,
            CollectionItem.position,
            CollectionItem.added_at,
            CollectionItem.note,
            Asset.title.label("asset_title"),
            Asset.asset_type.label("asset_type"),
            Asset.duration_ms.label("asset_duration_ms"),
        )
        .join(Asset, Asset.id == CollectionItem.asset_id)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.position)
    )

    items_result = await db.execute(items_query)
    items = [
        CollectionItemWithAsset(
            id=row.id,
            asset_id=row.asset_id,
            position=row.position,
            added_at=row.added_at,
            note=row.note,
            asset_title=row.asset_title,
            asset_type=row.asset_type,
            asset_duration_ms=row.asset_duration_ms,
        )
        for row in items_result.all()
    ]

    return CollectionWithItems(
        **CollectionRead.model_validate(collection).model_dump(),
        items=items,
    )


@router.patch("/{collection_id}", response_model=CollectionRead)
async def update_collection(
    collection_id: UUID,
    data: CollectionUpdate,
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Update a collection.
    """
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Check ownership
    if collection.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized to update this collection")

    if collection.is_locked:
        raise HTTPException(status_code=400, detail="Collection is locked")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(collection, field, value)

    collection.updated_by = current_user.id
    await db.flush()
    await db.refresh(collection)

    logger.info(f"Collection {collection_id} updated by user {current_user.id}")
    return CollectionRead.model_validate(collection)


@router.delete("/{collection_id}", response_model=MessageResponse)
async def delete_collection(
    collection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Delete a collection and all its items.
    """
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Check ownership
    if collection.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized to delete this collection")

    if collection.is_locked:
        raise HTTPException(status_code=400, detail="Collection is locked")

    await db.delete(collection)
    await db.flush()

    logger.info(f"Collection {collection_id} deleted by user {current_user.id}")
    return MessageResponse(message="Collection deleted", id=collection_id)


# =============================================================================
# Collection Items Endpoints
# =============================================================================


@router.post("/{collection_id}/items", response_model=CollectionItemRead, status_code=201)
async def add_item_to_collection(
    collection_id: UUID,
    data: CollectionItemCreate,
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Add an asset to a collection.
    """
    # Get collection
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Check permission
    if collection.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    if collection.is_locked:
        raise HTTPException(status_code=400, detail="Collection is locked")

    # Check if asset exists
    asset_result = await db.execute(
        select(Asset).where(Asset.id == data.asset_id)
    )
    if not asset_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Asset not found")

    # Check for duplicate
    existing = await db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.asset_id == data.asset_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Asset already in collection")

    # Get next position if not specified
    if data.position is None:
        max_pos_result = await db.execute(
            select(func.coalesce(func.max(CollectionItem.position), -1))
            .where(CollectionItem.collection_id == collection_id)
        )
        data.position = (max_pos_result.scalar() or -1) + 1

    item = CollectionItem(
        collection_id=collection_id,
        asset_id=data.asset_id,
        tenant_id=collection.tenant_id,
        position=data.position,
        added_by=current_user.id,
        note=data.note,
    )

    db.add(item)

    # Update item count
    collection.item_count += 1

    await db.flush()
    await db.refresh(item)

    logger.info(f"Asset {data.asset_id} added to collection {collection_id}")
    return CollectionItemRead.model_validate(item)


@router.post("/{collection_id}/items/bulk", response_model=MessageResponse)
async def bulk_add_items(
    collection_id: UUID,
    data: BulkAddItemsRequest,
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Add multiple assets to a collection at once.
    """
    # Get collection
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    if collection.is_locked:
        raise HTTPException(status_code=400, detail="Collection is locked")

    # Get current max position
    max_pos_result = await db.execute(
        select(func.coalesce(func.max(CollectionItem.position), -1))
        .where(CollectionItem.collection_id == collection_id)
    )
    position = (max_pos_result.scalar() or -1) + 1

    added_count = 0
    for asset_id in data.asset_ids:
        # Skip if already exists
        existing = await db.execute(
            select(CollectionItem).where(
                CollectionItem.collection_id == collection_id,
                CollectionItem.asset_id == asset_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        item = CollectionItem(
            collection_id=collection_id,
            asset_id=asset_id,
            tenant_id=collection.tenant_id,
            position=position,
            added_by=current_user.id,
        )
        db.add(item)
        position += 1
        added_count += 1

    # Update item count
    collection.item_count += added_count
    await db.flush()

    logger.info(f"Bulk added {added_count} assets to collection {collection_id}")
    return MessageResponse(message=f"Added {added_count} items to collection")


@router.delete("/{collection_id}/items/{asset_id}", response_model=MessageResponse)
async def remove_item_from_collection(
    collection_id: UUID,
    asset_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Remove an asset from a collection.
    """
    # Get collection
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    if collection.is_locked:
        raise HTTPException(status_code=400, detail="Collection is locked")

    # Get item
    item_result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.asset_id == asset_id,
        )
    )
    item = item_result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found in collection")

    await db.delete(item)

    # Update item count
    collection.item_count = max(0, collection.item_count - 1)
    await db.flush()

    logger.info(f"Asset {asset_id} removed from collection {collection_id}")
    return MessageResponse(message="Item removed from collection")


@router.post("/{collection_id}/items/reorder", response_model=MessageResponse)
async def reorder_collection_items(
    collection_id: UUID,
    data: ReorderItemsRequest,
    db: DbSession,
    current_user: CurrentActiveUser,
):
    """
    Reorder items in a collection.
    """
    # Get collection
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    if collection.is_locked:
        raise HTTPException(status_code=400, detail="Collection is locked")

    # Update positions
    for position, item_id in enumerate(data.item_ids):
        await db.execute(
            select(CollectionItem)
            .where(CollectionItem.id == item_id)
            .with_for_update()
        )
        item_result = await db.execute(
            select(CollectionItem).where(CollectionItem.id == item_id)
        )
        item = item_result.scalar_one_or_none()
        if item and item.collection_id == collection_id:
            item.position = position

    await db.flush()

    logger.info(f"Collection {collection_id} items reordered")
    return MessageResponse(message="Items reordered successfully")
