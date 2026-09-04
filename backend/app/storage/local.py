"""Local-disk backend for development and tests.

Serves files through the API with HMAC-signed, expiring URLs so the access model
matches S3 presigned URLs exactly (the frontend cannot tell the difference).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from app.core.config import settings
from app.storage.base import StorageBackend, StoredObject


def _sign(payload: str) -> str:
    digest = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def sign_local_url(key: str, expires_at: int, method: str = "GET") -> str:
    return _sign(f"{method}:{key}:{expires_at}")


def verify_local_signature(key: str, expires_at: int, signature: str, method: str = "GET") -> bool:
    if expires_at < int(time.time()):
        return False
    return hmac.compare_digest(sign_local_url(key, expires_at, method), signature)


class LocalStorage(StorageBackend):
    name = "local"

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.storage_local_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError("invalid storage key")
        return p

    def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(p)
        (p.parent / (p.name + ".ctype")).write_text(content_type)
        return StoredObject(key=key, size_bytes=len(data), content_type=content_type)

    def put_file(self, key: str, path: str | Path, content_type: str) -> StoredObject:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, p)
        (p.parent / (p.name + ".ctype")).write_text(content_type)
        return StoredObject(key=key, size_bytes=p.stat().st_size, content_type=content_type)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def content_type(self, key: str) -> str:
        p = self._path(key)
        meta = p.parent / (p.name + ".ctype")
        if meta.exists():
            return meta.read_text().strip()
        import mimetypes

        return mimetypes.guess_type(p.name)[0] or "application/octet-stream"

    def download_to(self, key: str, path: str | Path) -> Path:
        dst = Path(path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._path(key), dst)
        return dst

    def local_path(self, key: str) -> Path:
        return self._path(key)

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()
        meta = p.parent / (p.name + ".ctype")
        if meta.exists():
            meta.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def signed_get_url(self, key: str, expires_seconds: int | None = None, *, filename: str | None = None) -> str:
        exp = int(time.time()) + (expires_seconds or settings.signed_url_expire_seconds)
        sig = sign_local_url(key, exp, "GET")
        url = f"{settings.api_v1_prefix}/media/files/{quote(key)}?expires={exp}&signature={sig}"
        if filename:
            url += f"&download={quote(filename)}"
        return url

    def signed_put_url(self, key: str, content_type: str, expires_seconds: int | None = None) -> str:
        exp = int(time.time()) + (expires_seconds or 900)
        sig = sign_local_url(key, exp, "PUT")
        return f"{settings.api_v1_prefix}/media/files/{quote(key)}?expires={exp}&signature={sig}"

    def health(self) -> bool:
        return self.root.exists()
