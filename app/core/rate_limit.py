"""
AKASHI MAM API - Rate Limiting
Redis-based rate limiting middleware.
"""

import logging
from datetime import datetime
from typing import Callable, Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from redis import asyncio as aioredis

from app.core.config import settings


logger = logging.getLogger(__name__)

# Redis connection (lazy initialization)
_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Get or create Redis connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


class RateLimiter:
    """
    Redis-based rate limiter using sliding window algorithm.
    """

    def __init__(
        self,
        requests: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "rate_limit",
    ):
        """
        Initialize rate limiter.

        Args:
            requests: Maximum requests allowed in the window
            window_seconds: Window size in seconds
            key_prefix: Redis key prefix
        """
        self.requests = requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    def _get_key(self, identifier: str) -> str:
        """Generate Redis key for the identifier."""
        return f"{self.key_prefix}:{identifier}"

    async def is_allowed(self, identifier: str) -> tuple[bool, dict]:
        """
        Check if request is allowed for the identifier.

        Args:
            identifier: Unique identifier (IP, user_id, etc.)

        Returns:
            Tuple of (allowed, info_dict)
        """
        if not settings.rate_limit_enabled:
            return True, {"remaining": -1, "reset": 0}

        try:
            redis = await get_redis()
            key = self._get_key(identifier)
            now = datetime.now().timestamp()

            # Use pipeline for atomic operations
            pipe = redis.pipeline()

            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, now - self.window_seconds)

            # Count current requests in window
            pipe.zcard(key)

            # Execute pipeline
            results = await pipe.execute()
            current_count = results[1]

            if current_count >= self.requests:
                # Get time until oldest entry expires
                oldest = await redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_time = int(oldest[0][1] + self.window_seconds - now)
                else:
                    reset_time = self.window_seconds

                return False, {
                    "remaining": 0,
                    "reset": reset_time,
                    "limit": self.requests,
                    "current": current_count,
                }

            # Add current request
            await redis.zadd(key, {str(now): now})

            # Set expiration on the key
            await redis.expire(key, self.window_seconds + 10)

            remaining = self.requests - current_count - 1
            return True, {
                "remaining": max(0, remaining),
                "reset": self.window_seconds,
                "limit": self.requests,
                "current": current_count + 1,
            }

        except Exception as e:
            # If Redis fails, allow the request (fail open)
            logger.error(f"Rate limiter error: {e}")
            return True, {"remaining": -1, "reset": 0, "error": str(e)}

    async def reset(self, identifier: str) -> bool:
        """Reset rate limit for an identifier."""
        try:
            redis = await get_redis()
            key = self._get_key(identifier)
            await redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Rate limiter reset error: {e}")
            return False


# Default rate limiter instance
default_limiter = RateLimiter(
    requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    # Check for forwarded headers (reverse proxy)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip

    # Fallback to direct client
    if request.client:
        return request.client.host

    return "unknown"


async def rate_limit_middleware(request: Request, call_next: Callable):
    """
    Rate limiting middleware.
    """
    # Skip rate limiting for certain paths
    skip_paths = ["/api/v1/health", "/docs", "/redoc", "/openapi.json"]
    if any(request.url.path.startswith(p) for p in skip_paths):
        return await call_next(request)

    # Get identifier (prefer user_id from JWT, fallback to IP)
    identifier = get_client_ip(request)

    # Check if authenticated (extract from state if available)
    if hasattr(request.state, "user_id") and request.state.user_id:
        identifier = f"user:{request.state.user_id}"
    else:
        identifier = f"ip:{identifier}"

    # Check rate limit
    allowed, info = await default_limiter.is_allowed(identifier)

    if not allowed:
        logger.warning(f"Rate limit exceeded for {identifier}")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded",
                "retry_after": info.get("reset", 60),
            },
            headers={
                "X-RateLimit-Limit": str(info.get("limit", 100)),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info.get("reset", 60)),
                "Retry-After": str(info.get("reset", 60)),
            },
        )

    # Process request
    response = await call_next(request)

    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = str(info.get("limit", 100))
    response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))
    response.headers["X-RateLimit-Reset"] = str(info.get("reset", 60))

    return response


# Dependency for route-specific rate limiting
class RateLimitDepends:
    """
    Dependency for route-specific rate limiting.

    Usage:
        @router.post("/heavy-operation")
        async def heavy_operation(
            _: None = Depends(RateLimitDepends(requests=10, window_seconds=60))
        ):
            ...
    """

    def __init__(self, requests: int = 10, window_seconds: int = 60, key_prefix: str = "route"):
        self.limiter = RateLimiter(
            requests=requests,
            window_seconds=window_seconds,
            key_prefix=key_prefix,
        )

    async def __call__(self, request: Request) -> None:
        identifier = get_client_ip(request)

        if hasattr(request.state, "user_id") and request.state.user_id:
            identifier = f"user:{request.state.user_id}"
        else:
            identifier = f"ip:{identifier}"

        # Add route path to make it route-specific
        identifier = f"{identifier}:{request.url.path}"

        allowed, info = await self.limiter.is_allowed(identifier)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "Rate limit exceeded for this endpoint",
                    "retry_after": info.get("reset", 60),
                },
                headers={
                    "Retry-After": str(info.get("reset", 60)),
                },
            )
