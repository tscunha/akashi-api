"""
AKASHI MAM API - API v1 Router
"""

from fastapi import APIRouter

from app.api.v1.endpoints import assets, health, upload


api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(assets.router, prefix="/assets", tags=["Assets"])
api_router.include_router(upload.router, tags=["Upload"])
