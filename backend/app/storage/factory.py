from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.storage.base import StorageBackend


@lru_cache
def get_storage() -> StorageBackend:
    if settings.storage_backend == "s3":
        from app.storage.s3 import S3Storage

        return S3Storage()
    from app.storage.local import LocalStorage

    return LocalStorage()
