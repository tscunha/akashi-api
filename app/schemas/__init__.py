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
from app.schemas.keyword import (
    KeywordCreate,
    KeywordUpdate,
    KeywordRead,
    KeywordSummary,
    KeywordSearchResult,
    KeywordListResponse,
)
from app.schemas.marker import (
    MarkerCreate,
    MarkerUpdate,
    MarkerRead,
    MarkerSummary,
    MarkerListResponse,
)
from app.schemas.auth import (
    Token,
    TokenPair,
    TokenPayload,
    RefreshTokenRequest,
    LoginRequest,
    LoginResponse,
    LoginResponseV2,
    UserCreate,
    UserUpdate,
    UserRead,
    UserSummary,
    PasswordChange,
)
from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionRead,
    CollectionSummary,
    CollectionListResponse,
    CollectionItemCreate,
    CollectionItemUpdate,
    CollectionItemRead,
    CollectionItemWithAsset,
    CollectionWithItems,
    BulkAddItemsRequest,
    ReorderItemsRequest,
)
from app.schemas.search import (
    SearchQuery,
    SearchResult,
    SearchResponse,
    SearchSuggestion,
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
    # Keyword
    "KeywordCreate",
    "KeywordUpdate",
    "KeywordRead",
    "KeywordSummary",
    "KeywordSearchResult",
    "KeywordListResponse",
    # Marker
    "MarkerCreate",
    "MarkerUpdate",
    "MarkerRead",
    "MarkerSummary",
    "MarkerListResponse",
    # Auth
    "Token",
    "TokenPair",
    "TokenPayload",
    "RefreshTokenRequest",
    "LoginRequest",
    "LoginResponse",
    "LoginResponseV2",
    "UserCreate",
    "UserUpdate",
    "UserRead",
    "UserSummary",
    "PasswordChange",
    # Collection
    "CollectionCreate",
    "CollectionUpdate",
    "CollectionRead",
    "CollectionSummary",
    "CollectionListResponse",
    "CollectionItemCreate",
    "CollectionItemUpdate",
    "CollectionItemRead",
    "CollectionItemWithAsset",
    "CollectionWithItems",
    "BulkAddItemsRequest",
    "ReorderItemsRequest",
    # Search
    "SearchQuery",
    "SearchResult",
    "SearchResponse",
    "SearchSuggestion",
]
