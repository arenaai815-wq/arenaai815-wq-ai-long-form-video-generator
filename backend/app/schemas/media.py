from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AudioKind, MediaKind, MediaSource
from app.schemas.common import ORMModel


class MediaAssetPublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    scene_id: uuid.UUID | None
    kind: MediaKind
    source: MediaSource
    filename: str
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_seconds: float | None
    fps: float | None
    prompt: str | None
    provider: str | None
    tags: list[Any]
    is_reusable: bool
    is_uploaded: bool
    created_at: datetime
    url: str | None = None
    thumbnail_url: str | None = None


class AudioAssetPublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    kind: AudioKind
    source: MediaSource
    filename: str
    content_type: str
    size_bytes: int
    duration_seconds: float | None
    mood: str | None
    bpm: int | None
    license: str | None
    tags: list[Any]
    is_system: bool
    created_at: datetime
    url: str | None = None


class UploadInitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=120)
    size_bytes: int = Field(ge=1, le=5 * 1024**3)
    project_id: uuid.UUID | None = None
    kind: MediaKind | None = None  # inferred from content_type if omitted
    audio_kind: AudioKind | None = None  # for audio uploads: music / sfx / voiceover


class UploadInitResponse(BaseModel):
    upload_url: str
    storage_key: str
    method: str = "PUT"
    headers: dict[str, str] = Field(default_factory=dict)
    expires_in: int


class UploadCompleteRequest(BaseModel):
    storage_key: str
    filename: str
    content_type: str
    project_id: uuid.UUID | None = None
    kind: MediaKind | None = None
    audio_kind: AudioKind | None = None
    tags: list[str] = Field(default_factory=list)
    is_reusable: bool = True


class MediaUpdate(BaseModel):
    filename: str | None = None
    tags: list[str] | None = None
    is_reusable: bool | None = None
    project_id: uuid.UUID | None = None


class StockSearchResult(BaseModel):
    id: str
    kind: str
    url: str
    download_url: str
    thumbnail_url: str | None
    width: int | None
    height: int | None
    duration_seconds: float | None
    author: str | None
    source: str
    license: str


class StockImportRequest(BaseModel):
    item: StockSearchResult
    project_id: uuid.UUID | None = None
    scene_id: uuid.UUID | None = None


class StorageUsage(BaseModel):
    used_bytes: int
    limit_bytes: int
    by_kind: dict[str, int]
    asset_count: int
