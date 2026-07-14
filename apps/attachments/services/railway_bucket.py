"""Railway Bucket storage backend (S3-compatible).

Uses boto3 to interact with Railway's S3-compatible object storage.
Objects are private by default. No public URLs are generated.
Storage keys are opaque and server-generated.
"""

from typing import BinaryIO, Optional

from botocore.exceptions import ClientError, BotoCoreError
from django.conf import settings

from apps.attachments.services.base import AttachmentStorageBackend, StoredObject


def _is_missing(exc: ClientError) -> bool:
    """Check if ClientError is 404/NotFound."""
    code = exc.response["Error"]["Code"]
    return code == "404" or code == "NotFound"


class RailwayBucketStorageBackend(AttachmentStorageBackend):
    """S3-compatible adapter for Railway Bucket."""

    def __init__(self) -> None:
        self._client = self._build_client()
        self._bucket = settings.RAILWAY_BUCKET_NAME

    # ── helpers ──────────────────────────────────────────────────────────────

    def _build_client(self):
        import boto3
        from botocore.config import Config as BotoConfig

        cfg = BotoConfig(
            connect_timeout=settings.RAILWAY_BUCKET_CONNECT_TIMEOUT,
            read_timeout=settings.RAILWAY_BUCKET_READ_TIMEOUT,
            retries={"max_attempts": settings.RAILWAY_BUCKET_MAX_RETRIES},
            signature_version="s3v4",
            s3={
                "addressing_style": settings.RAILWAY_BUCKET_ADDRESSING_STYLE,
            },
        )
        return boto3.client(
            "s3",
            endpoint_url=settings.RAILWAY_BUCKET_ENDPOINT,
            aws_access_key_id=settings.RAILWAY_BUCKET_ACCESS_KEY,
            aws_secret_access_key=settings.RAILWAY_BUCKET_SECRET_KEY,
            region_name=settings.RAILWAY_BUCKET_REGION,
            config=cfg,
        )

    def _normalise_key(self, storage_key: str) -> str:
        """Ensure no leading slash — S3 treats leading slash as literal part of key."""
        return storage_key.lstrip("/")

    # ── interface ────────────────────────────────────────────────────────────

    def save(self, file: BinaryIO, storage_key: str) -> StoredObject:
        key = self._normalise_key(storage_key)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=file,
        )
        resp = self._client.head_object(Bucket=self._bucket, Key=key)
        size_bytes = resp.get("ContentLength", 0)
        return StoredObject(
            storage_key=storage_key,
            provider="railway_bucket",
            size_bytes=size_bytes,
        )

    def open(self, storage_key: str) -> Optional[BinaryIO]:
        key = self._normalise_key(storage_key)
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"]
        except ClientError as exc:
            if _is_missing(exc):
                return None
            raise
        except BotoCoreError:
            return None

    def delete(self, storage_key: str) -> bool:
        key = self._normalise_key(storage_key)
        if not self.exists(storage_key):
            return False
        self._client.delete_object(Bucket=self._bucket, Key=key)
        return True

    def exists(self, storage_key: str) -> bool:
        key = self._normalise_key(storage_key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if _is_missing(exc):
                return False
            raise
        except BotoCoreError:
            return False

    def size(self, storage_key: str) -> Optional[int]:
        key = self._normalise_key(storage_key)
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
            return resp.get("ContentLength")
        except ClientError as exc:
            if _is_missing(exc):
                return None
            raise
        except BotoCoreError:
            return None

    def metadata(self, storage_key: str) -> dict:
        key = self._normalise_key(storage_key)
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
            return {
                "exists": True,
                "size_bytes": resp.get("ContentLength", 0),
                "etag": resp.get("ETag", "").strip('"'),
                "last_modified": resp.get("LastModified").isoformat()
                if resp.get("LastModified")
                else None,
                "provider": "railway_bucket",
            }
        except ClientError as exc:
            if _is_missing(exc):
                return {"exists": False}
            raise
        except BotoCoreError:
            return {"exists": False}

    def generate_internal_reference(self, storage_key: str) -> str:
        return f"railway_bucket://{self._bucket}/{storage_key}"

    # ── readiness ────────────────────────────────────────────────────────────

    def check_access(self) -> bool:
        """Verify the backend can reach the bucket (list buckets or head bucket)."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return True
        except Exception:
            return False
