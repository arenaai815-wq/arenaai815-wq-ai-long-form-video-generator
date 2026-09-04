from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.project import CaptionStyleSettings


class CaptionWord(BaseModel):
    word: str
    start: float
    end: float


class CaptionCue(BaseModel):
    index: int
    start: float
    end: float
    text: str
    scene_id: uuid.UUID | str | None = None
    words: list[CaptionWord] = Field(default_factory=list)


class CaptionPublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    language: str
    cues: list[Any]
    style: dict[str, Any]
    source: str
    provider: str | None
    is_current: bool
    cue_count: int
    created_at: datetime
    updated_at: datetime
    srt_url: str | None = None
    vtt_url: str | None = None


class CaptionGenerateRequest(BaseModel):
    mode: str = Field(default="auto", pattern="^(auto|tts_timings|transcribe)$")
    language: str | None = None
    style: CaptionStyleSettings | None = None
    max_chars_per_line: int | None = Field(default=None, ge=16, le=90)
    max_lines: int | None = Field(default=None, ge=1, le=3)


class CaptionUpdate(BaseModel):
    cues: list[CaptionCue] | None = None
    style: CaptionStyleSettings | None = None
    language: str | None = None
