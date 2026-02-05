"""
AKASHI MAM API - Asset Service
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Asset, AssetStorageLocation, AssetTechnicalMetadata, Tenant


class AssetService:
    """Service for asset CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_tenant_by_code(self, code: str) -> Tenant | None:
        """Get tenant by code."""
        result = await self.db.execute(
            select(Tenant).where(Tenant.code == code, Tenant.is_active == True)
        )
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        asset_id: UUID,
        include_deleted: bool = False,
    ) -> Asset | None:
        """Get asset by ID."""
        query = select(Asset).where(Asset.id == asset_id)

        if not include_deleted:
            query = query.where(Asset.deleted_at.is_(None))

        query = query.options(
            selectinload(Asset.storage_locations),
            selectinload(Asset.technical_metadata),
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: UUID | None = None,
        asset_type: str | None = None,
        status: str | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Asset], int]:
        """List assets with filters and pagination."""
        query = select(Asset).where(Asset.deleted_at.is_(None))

        if tenant_id:
            query = query.where(Asset.tenant_id == tenant_id)

        if asset_type:
            query = query.where(Asset.asset_type == asset_type)

        if status:
            query = query.where(Asset.status == status)

        if search:
            query = query.where(Asset.title.ilike(f"%{search}%"))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination
        query = query.order_by(Asset.created_at.desc()).offset(offset).limit(limit)

        result = await self.db.execute(query)
        assets = list(result.scalars().all())

        return assets, total

    async def create(
        self,
        tenant_id: UUID,
        title: str,
        asset_type: str,
        **kwargs: Any,
    ) -> Asset:
        """Create a new asset."""
        asset = Asset(
            tenant_id=tenant_id,
            title=title,
            asset_type=asset_type,
            status="ingesting",
            **kwargs,
        )
        self.db.add(asset)
        await self.db.flush()
        await self.db.refresh(asset)
        return asset

    async def update(
        self,
        asset: Asset,
        **kwargs: Any,
    ) -> Asset:
        """Update an asset."""
        for key, value in kwargs.items():
            if hasattr(asset, key) and value is not None:
                setattr(asset, key, value)

        await self.db.flush()
        await self.db.refresh(asset)
        return asset

    async def soft_delete(self, asset: Asset, deleted_by: UUID | None = None) -> Asset:
        """Soft delete an asset."""
        asset.deleted_at = datetime.utcnow()
        asset.deleted_by = deleted_by
        asset.status = "deleted"
        await self.db.flush()
        return asset

    async def restore(self, asset: Asset) -> Asset:
        """Restore a soft-deleted asset."""
        asset.deleted_at = None
        asset.deleted_by = None
        asset.status = "available"
        await self.db.flush()
        return asset

    async def add_storage_location(
        self,
        asset: Asset,
        storage_type: str,
        bucket: str,
        path: str,
        purpose: str = "original",
        **kwargs: Any,
    ) -> AssetStorageLocation:
        """Add a storage location to an asset."""
        location = AssetStorageLocation(
            asset_id=asset.id,
            tenant_id=asset.tenant_id,
            storage_type=storage_type,
            bucket=bucket,
            path=path,
            purpose=purpose,
            **kwargs,
        )
        self.db.add(location)
        await self.db.flush()
        return location

    async def add_technical_metadata(
        self,
        asset: Asset,
        **kwargs: Any,
    ) -> AssetTechnicalMetadata:
        """Add or update technical metadata for an asset."""
        # Check if metadata already exists
        result = await self.db.execute(
            select(AssetTechnicalMetadata).where(
                AssetTechnicalMetadata.asset_id == asset.id
            )
        )
        metadata = result.scalar_one_or_none()

        if metadata:
            # Update existing
            for key, value in kwargs.items():
                if hasattr(metadata, key):
                    setattr(metadata, key, value)
        else:
            # Create new
            metadata = AssetTechnicalMetadata(
                asset_id=asset.id,
                tenant_id=asset.tenant_id,
                **kwargs,
            )
            self.db.add(metadata)

        await self.db.flush()
        return metadata

    async def update_status(self, asset: Asset, status: str) -> Asset:
        """Update asset status."""
        asset.status = status
        await self.db.flush()
        return asset
