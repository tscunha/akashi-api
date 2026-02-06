"""
AKASHI MAM API - API v1 Router
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    api_keys,
    assets,
    auth,
    collections,
    health,
    jobs,
    keywords,
    markers,
    search,
    upload,
)
from app.api.v1.endpoints import transcriptions, faces, scenes


api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(assets.router, prefix="/assets", tags=["Assets"])
api_router.include_router(collections.router, prefix="/collections", tags=["Collections"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(upload.router, tags=["Upload"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])

# Keywords and Markers (routes include /assets/{id}/keywords and /keywords/{id})
api_router.include_router(keywords.router, tags=["Keywords"])
api_router.include_router(markers.router, tags=["Markers"])

# AI Processing endpoints
api_router.include_router(transcriptions.router, prefix="/assets", tags=["Transcriptions"])
api_router.include_router(faces.router, tags=["Faces & Persons"])
api_router.include_router(scenes.router, prefix="/assets", tags=["Scene Descriptions"])

# API Keys (for MCP and external integrations)
api_router.include_router(api_keys.router, tags=["API Keys"])

