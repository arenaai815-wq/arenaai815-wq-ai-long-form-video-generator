from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ResearchStatistic(BaseModel):
    value: str
    context: str
    source: str | None = None


class ResearchSource(BaseModel):
    title: str
    url: str | None = None
    note: str | None = None


class ResearchSection(BaseModel):
    title: str
    key_points: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    statistics: list[ResearchStatistic] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    narrative_hooks: list[str] = Field(default_factory=list)


class ResearchPublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    summary: str | None
    sections: list[dict[str, Any]]
    key_facts: list[Any]
    statistics: list[Any]
    sources: list[Any]
    suggested_angles: list[Any]
    keywords: list[Any]
    provider: str | None
    model: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResearchUpdate(BaseModel):
    summary: str | None = None
    sections: list[ResearchSection] | None = None
    key_facts: list[str] | None = None
    statistics: list[ResearchStatistic] | None = None
    sources: list[ResearchSource] | None = None
    suggested_angles: list[str] | None = None
    keywords: list[str] | None = None
    approved: bool | None = None


class ResearchGenerateRequest(BaseModel):
    section_count: int = Field(default=6, ge=3, le=14)
    depth: str = Field(default="standard", pattern="^(quick|standard|deep)$")
    focus: str | None = Field(default=None, max_length=500)
    include_sources: bool = True
