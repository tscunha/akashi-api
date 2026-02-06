"""
AKASHI MAM API - Configuration Settings
"""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AKASHI MAM API"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-this-to-a-random-secret-key-in-production"

    # API
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://akashi:akashi_dev_2025@localhost:5432/akashi_mam",
        description="PostgreSQL connection string",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Object Storage (MinIO/S3)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "akashi"
    s3_secret_key: str = "akashi_minio_2025"
    s3_bucket_originals: str = "akashi-originals"
    s3_bucket_proxies: str = "akashi-proxies"
    s3_bucket_thumbnails: str = "akashi-thumbnails"
    s3_region: str = "us-east-1"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "amqp://akashi:akashi_rabbit_2025@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/1"

    # JWT Authentication
    jwt_secret_key: str = "change-this-jwt-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    jwt_refresh_token_rotate: bool = True  # Issue new refresh token on use

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100  # Requests per window
    rate_limit_window_seconds: int = 60  # Window size in seconds

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Processing
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    proxy_preset: str = "medium"
    proxy_crf: int = 23
    proxy_resolution: str = "1280x720"
    thumbnail_width: int = 320
    thumbnail_height: int = 180

    # Upload
    max_upload_size_mb: int = 10240  # 10GB
    chunk_size_mb: int = 10

    # AI Processing - Whisper
    whisper_mode: str = "local"  # local or api
    whisper_model: str = "base"  # tiny, base, small, medium, large-v3
    whisper_language: str = "pt"
    whisper_device: str = "cpu"  # cuda or cpu

    # AI Processing - Face Recognition
    face_model: str = "buffalo_l"  # InsightFace model
    face_min_confidence: float = 0.5
    face_sample_interval: float = 1.0  # seconds between samples

    # AI Processing - Vision
    vision_mode: str = "api"  # api or local
    vision_model: str = "gpt-4-vision-preview"
    vision_sample_interval: int = 10  # seconds between frames

    # OpenAI API
    openai_api_key: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        """Return max upload size in bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env.lower() in ("development", "dev", "local")

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience instance
settings = get_settings()
