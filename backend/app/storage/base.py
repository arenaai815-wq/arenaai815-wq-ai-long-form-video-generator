"""Object storage interface. Large binaries never touch PostgreSQL."""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredObject:
    key: str
    size_bytes: int
    content_type: str
    etag: str | None = None


def build_key(user_id: str | uuid.UUID, category: str, filename: str, project_id: str | uuid.UUID | None = None) -> str:
    """Deterministic, collision-free, tenant-scoped key layout.

    users/{user}/projects/{project}/{category}/{uuid}-{filename}
    """
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[-120:]
    parts = ["users", str(user_id)]
    if project_id:
        parts += ["projects", str(project_id)]
    parts += [category, f"{uuid.uuid4().hex}-{safe}"]
    return "/".join(parts)


class StorageBackend(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject: ...

    @abc.abstractmethod
    def put_file(self, key: str, path: str | Path, content_type: str) -> StoredObject: ...

    @abc.abstractmethod
    def get_bytes(self, key: str) -> bytes: ...

    @abc.abstractmethod
    def download_to(self, key: str, path: str | Path) -> Path: ...

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...

    @abc.abstractmethod
    def exists(self, key: str) -> bool: ...

    @abc.abstractmethod
    def signed_get_url(self, key: str, expires_seconds: int | None = None, *, filename: str | None = None) -> str: ...

    @abc.abstractmethod
    def signed_put_url(self, key: str, content_type: str, expires_seconds: int | None = None) -> str: ...

    @abc.abstractmethod
    def size(self, key: str) -> int: ...

    def health(self) -> bool:
        return True
