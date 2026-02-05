"""
AKASHI MAM API - Common Schemas
"""

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseSchema, Generic[T]):
    """Generic paginated response."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


class ErrorDetail(BaseSchema):
    """Error detail for validation errors."""

    loc: list[str | int]
    msg: str
    type: str


class ErrorResponse(BaseSchema):
    """Standard error response."""

    detail: str
    code: str | None = None
    errors: list[ErrorDetail] | None = None


class HealthResponse(BaseSchema):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
    database: str = "ok"
    storage: str = "ok"


class MessageResponse(BaseSchema):
    """Simple message response."""

    message: str
    id: UUID | None = None
