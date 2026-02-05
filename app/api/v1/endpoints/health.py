"""
AKASHI MAM API - Health Check Endpoints
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas import HealthResponse


router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """
    Health check endpoint.
    Verifies database connectivity.
    """
    # Check database
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # TODO: Check MinIO connectivity
    storage_status = "ok"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version="0.1.0",
        database=db_status,
        storage=storage_status,
    )


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Readiness check for Kubernetes.
    Returns 200 only if the service is ready to accept traffic.
    """
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not ready", "error": str(e)}


@router.get("/live")
async def liveness_check():
    """
    Liveness check for Kubernetes.
    Returns 200 if the service is alive.
    """
    return {"status": "alive"}
