"""
AKASHI MAM API - Storage Service (MinIO/S3)
"""

from datetime import datetime, timedelta
from typing import BinaryIO
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings


class StorageService:
    """Service for interacting with MinIO/S3 object storage."""

    def __init__(self):
        self.endpoint_url = settings.s3_endpoint_url
        self.access_key = settings.s3_access_key
        self.secret_key = settings.s3_secret_key
        self.region = settings.s3_region

        self.bucket_originals = settings.s3_bucket_originals
        self.bucket_proxies = settings.s3_bucket_proxies
        self.bucket_thumbnails = settings.s3_bucket_thumbnails

        # Create S3 client
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version="s3v4"),
        )

    async def ensure_buckets_exist(self) -> None:
        """Create buckets if they don't exist."""
        buckets = [self.bucket_originals, self.bucket_proxies, self.bucket_thumbnails]

        for bucket in buckets:
            try:
                self._client.head_bucket(Bucket=bucket)
            except ClientError:
                self._client.create_bucket(Bucket=bucket)

    def _generate_path(
        self,
        filename: str,
        asset_id: str,
        tenant_code: str,
        purpose: str = "original",
    ) -> str:
        """Generate a storage path for a file."""
        # Structure: tenant/year/month/asset_id/purpose/filename
        now = datetime.utcnow()
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""

        # Clean filename
        clean_name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

        return f"{tenant_code}/{now.year}/{now.month:02d}/{asset_id}/{purpose}/{clean_name}"

    async def upload_file(
        self,
        content: bytes,
        filename: str,
        asset_id: str,
        tenant_code: str,
        purpose: str = "original",
        bucket: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """
        Upload a file to storage.

        Args:
            content: File content as bytes
            filename: Original filename
            asset_id: Asset UUID
            tenant_code: Tenant code for path organization
            purpose: File purpose (original, proxy, thumbnail)
            bucket: Override bucket name
            content_type: MIME type

        Returns:
            Storage path (without bucket name)
        """
        if bucket is None:
            bucket = {
                "original": self.bucket_originals,
                "proxy": self.bucket_proxies,
                "thumbnail": self.bucket_thumbnails,
            }.get(purpose, self.bucket_originals)

        path = self._generate_path(filename, asset_id, tenant_code, purpose)

        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self._client.put_object(
            Bucket=bucket,
            Key=path,
            Body=content,
            **extra_args,
        )

        return path

    async def upload_fileobj(
        self,
        fileobj: BinaryIO,
        filename: str,
        asset_id: str,
        tenant_code: str,
        purpose: str = "original",
        bucket: str | None = None,
    ) -> str:
        """Upload a file-like object to storage."""
        if bucket is None:
            bucket = self.bucket_originals

        path = self._generate_path(filename, asset_id, tenant_code, purpose)

        self._client.upload_fileobj(
            fileobj,
            bucket,
            path,
        )

        return path

    async def download_file(self, bucket: str, path: str) -> bytes:
        """Download a file from storage."""
        response = self._client.get_object(Bucket=bucket, Key=path)
        return response["Body"].read()

    async def get_presigned_url(
        self,
        bucket: str,
        path: str,
        expires_in: int = 3600,
        method: str = "get_object",
    ) -> str:
        """
        Generate a presigned URL for accessing a file.

        Args:
            bucket: Bucket name
            path: Object path
            expires_in: URL expiration time in seconds
            method: S3 method (get_object, put_object)

        Returns:
            Presigned URL
        """
        return self._client.generate_presigned_url(
            method,
            Params={"Bucket": bucket, "Key": path},
            ExpiresIn=expires_in,
        )

    async def delete_file(self, bucket: str, path: str) -> None:
        """Delete a file from storage."""
        self._client.delete_object(Bucket=bucket, Key=path)

    async def file_exists(self, bucket: str, path: str) -> bool:
        """Check if a file exists in storage."""
        try:
            self._client.head_object(Bucket=bucket, Key=path)
            return True
        except ClientError:
            return False

    async def get_file_info(self, bucket: str, path: str) -> dict:
        """Get metadata about a file."""
        try:
            response = self._client.head_object(Bucket=bucket, Key=path)
            return {
                "size": response.get("ContentLength"),
                "content_type": response.get("ContentType"),
                "last_modified": response.get("LastModified"),
                "etag": response.get("ETag"),
            }
        except ClientError:
            return {}

    async def list_files(
        self,
        bucket: str,
        prefix: str = "",
        max_keys: int = 1000,
    ) -> list[dict]:
        """List files in a bucket with optional prefix."""
        response = self._client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            MaxKeys=max_keys,
        )

        files = []
        for obj in response.get("Contents", []):
            files.append({
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"],
            })

        return files
