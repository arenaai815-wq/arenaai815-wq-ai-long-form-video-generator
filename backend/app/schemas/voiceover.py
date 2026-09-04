from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class VoicePublic(BaseModel):
    id: str
    name: str
    language: str
    gender: str | None
    accent: str | None
    styles: list[str]
    preview_url: str | None
    provider: str
    is_premium: bool


class VoiceoverPublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    scene_id: uuid.UUID | None
    text: str
    provider: str
    voice_id: str
    voice_name: str | None
    language: str
    style: str | None
    speed: float
    content_type: str
    size_bytes: int
    duration_seconds: float | None
    word_timings: list[Any]
    status: str
    error: str | None
    is_current: bool
    created_at: datetime
    url: str | None = None


class VoiceoverGenerateRequest(BaseModel):
    scene_ids: list[uuid.UUID] | None = None  # None = every scene without a current voiceover
    force: bool = False
    voice_id: str | None = None
    provider: str | None = None
    language: str | None = None
    style: str | None = None
    speed: float | None = Field(default=None, ge=0.5, le=2.0)


class VoicePreviewRequest(BaseModel):
    text: str = Field(default="Welcome to the channel. Today we explore a story that changed everything.", max_length=400)
    voice_id: str
    provider: str | None = None
    language: str = "en"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    style: str | None = None
