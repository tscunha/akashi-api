"""
AKASHI MAM API - Pydantic Schemas
"""

from app.schemas.common import (
    BaseSchema,
    PaginationParams,
    PaginatedResponse,
    ErrorResponse,
    HealthResponse,
    MessageResponse,
)
from app.schemas.asset import (
    AssetCreate,
    AssetUpdate,
    AssetRead,
    AssetSummary,
    AssetListResponse,
    StorageLocationRead,
    TechnicalMetadataRead,
)
from app.schemas.upload import (
    IngestRequest,
    IngestResponse,
    UploadResponse,
    JobSummary,
    JobRead,
    PresignedUrlResponse,
)

__all__ = [
    # Common
    "BaseSchema",
    "PaginationParams",
    "PaginatedResponse",
    "ErrorResponse",
    "HealthResponse",
    "MessageResponse",
    # Asset
    "AssetCreate",
    "AssetUpdate",
    "AssetRead",
    "AssetSummary",
    "AssetListResponse",
    "StorageLocationRead",
    "TechnicalMetadataRead",
    # Upload
    "IngestRequest",
    "IngestResponse",
    "UploadResponse",
    "JobSummary",
    "JobRead",
    "PresignedUrlResponse",
]
