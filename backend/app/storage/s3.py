"""S3-compatible backend (AWS S3, MinIO, Cloudflare R2, Backblaze B2, DigitalOcean Spaces...)."""

from __future__ import annotations

from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.storage.base import StorageBackend, StoredObject


class S3Storage(StorageBackend):
    name = "s3"

    def __init__(self) -> None:
        self.bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path" if settings.s3_use_path_style else "auto"}),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                kwargs = {"Bucket": self.bucket}
                if settings.s3_region != "us-east-1" and not settings.s3_endpoint_url:
                    kwargs["CreateBucketConfiguration"] = {"LocationConstraint": settings.s3_region}
                self._client.create_bucket(**kwargs)
            except ClientError:
                pass  # bucket may be managed externally with no create permission

    def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        resp = self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return StoredObject(key=key, size_bytes=len(data), content_type=content_type, etag=resp.get("ETag"))

    def put_file(self, key: str, path: str | Path, content_type: str) -> StoredObject:
        p = Path(path)
        self._client.upload_file(str(p), self.bucket, key, ExtraArgs={"ContentType": content_type})
        return StoredObject(key=key, size_bytes=p.stat().st_size, content_type=content_type)

    def get_bytes(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def download_to(self, key: str, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self.bucket, key, str(p))
        return p

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def size(self, key: str) -> int:
        return int(self._client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])

    def signed_get_url(self, key: str, expires_seconds: int | None = None, *, filename: str | None = None) -> str:
        if settings.storage_public_base_url:
            return f"{settings.storage_public_base_url.rstrip('/')}/{key}"
        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self._client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=expires_seconds or settings.signed_url_expire_seconds
        )

    def signed_put_url(self, key: str, content_type: str, expires_seconds: int | None = None) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_seconds or min(settings.signed_url_expire_seconds, 900),
        )

    def health(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False
