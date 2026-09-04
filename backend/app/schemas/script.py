from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import SectionKind
from app.schemas.common import ORMModel


class ScriptSectionPublic(ORMModel):
    id: uuid.UUID
    script_id: uuid.UUID
    order_index: int
    kind: SectionKind
    heading: str
    content: str
    summary: str | None
    talking_points: list[Any]
    word_count: int
    estimated_duration_seconds: float
    is_locked: bool
    regeneration_count: int
    updated_at: datetime


class ScriptPublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    is_current: bool
    title: str | None
    hook: str | None
    outline: list[Any]
    word_count: int
    estimated_duration_seconds: float
    target_duration_minutes: int
    words_per_minute: int
    provider: str | None
    model: str | None
    notes: str | None
    sections: list[ScriptSectionPublic] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ScriptGenerateRequest(BaseModel):
    target_duration_minutes: int | None = Field(default=None, ge=1, le=180)
    tone: str | None = None
    instructions: str | None = Field(default=None, max_length=2000)
    words_per_minute: int | None = Field(default=None, ge=90, le=220)


class SectionRegenerateRequest(BaseModel):
    instructions: str | None = Field(default=None, max_length=2000)
    target_words: int | None = Field(default=None, ge=20, le=3000)
    tone: str | None = None


class SectionUpdate(BaseModel):
    heading: str | None = Field(default=None, max_length=200)
    content: str | None = None
    kind: SectionKind | None = None
    talking_points: list[str] | None = None
    is_locked: bool | None = None


class SectionCreate(BaseModel):
    heading: str = Field(max_length=200)
    content: str = ""
    kind: SectionKind = SectionKind.BODY
    after_section_id: uuid.UUID | None = None
    talking_points: list[str] = Field(default_factory=list)


class SectionReorder(BaseModel):
    section_ids: list[uuid.UUID]


class ScriptUpdate(BaseModel):
    title: str | None = None
    hook: str | None = None
    notes: str | None = None
    words_per_minute: int | None = Field(default=None, ge=90, le=220)


class ScriptStats(BaseModel):
    word_count: int
    estimated_duration_seconds: float
    target_duration_seconds: float
    sections: int
    words_per_minute: int
    delta_seconds: float
