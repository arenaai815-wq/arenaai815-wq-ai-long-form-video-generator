from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ProjectStatus
from app.schemas.common import ORMModel

ASPECT_RATIOS = ("16:9", "9:16", "1:1", "4:3")
RESOLUTIONS = ("720p", "1080p", "1440p", "4k")
VIDEO_FORMATS = (
    "documentary",
    "educational",
    "explainer",
    "commentary",
    "storytelling",
    "faceless",
    "podcast",
    "listicle",
    "news",
    "history",
    "true_crime",
    "finance",
    "science",
    "motivation",
    "review",
    "tutorial",
)
DURATION_PRESETS = (5, 10, 15, 20, 30, 45, 60, 90, 120)


class VoiceSettings(BaseModel):
    provider: str | None = None
    voice_id: str = "mock-aria"
    voice_name: str | None = None
    language: str = "en"
    style: str | None = "narration"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class CaptionStyleSettings(BaseModel):
    enabled: bool = True
    burn_in: bool = True
    font_family: str = "DejaVu Sans"
    font_size: int = Field(default=44, ge=16, le=120)
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: float = Field(default=2.0, ge=0, le=8)
    background_color: str | None = None
    position: Literal["top", "center", "bottom"] = "bottom"
    margin_v: int = Field(default=60, ge=0, le=600)
    animation: Literal["none", "fade", "pop", "karaoke"] = "none"
    max_chars_per_line: int = Field(default=42, ge=16, le=90)
    max_lines: int = Field(default=2, ge=1, le=3)
    timing_offset: float = Field(default=0.0, ge=-2, le=2)
    highlight_color: str = "#FFD400"


class MusicSettings(BaseModel):
    enabled: bool = True
    asset_id: uuid.UUID | None = None
    mood: str | None = "inspiring"
    volume: float = Field(default=0.12, ge=0, le=1)
    ducking: bool = True
    fade_in: float = 1.5
    fade_out: float = 3.0


class ProjectSettings(BaseModel):
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    captions: CaptionStyleSettings = Field(default_factory=CaptionStyleSettings)
    music: MusicSettings = Field(default_factory=MusicSettings)
    visuals: dict[str, Any] = Field(
        default_factory=lambda: {
            "mode": "ai_image",  # ai_image | ai_video | stock | mixed
            "ai_video_ratio": 0.0,  # share of scenes that use AI video when mode=mixed
            "motion": "ken_burns",
            "transition": "fade",
            "transition_duration": 0.6,
            "image_provider": None,
            "video_provider": None,
        }
    )
    intro: dict[str, Any] = Field(default_factory=lambda: {"enabled": True, "duration": 3.0, "title": None, "subtitle": None})
    outro: dict[str, Any] = Field(default_factory=lambda: {"enabled": True, "duration": 4.0, "text": "Thanks for watching", "cta": "Subscribe for more"})
    watermark: dict[str, Any] = Field(default_factory=lambda: {"enabled": False, "text": None, "asset_id": None, "position": "bottom_right", "opacity": 0.6})
    words_per_minute: int = Field(default=150, ge=90, le=220)
    scene_target_seconds: float = Field(default=9.0, ge=4, le=30)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=3, max_length=4000)
    description: str | None = None
    niche: str | None = Field(default=None, max_length=100)
    target_audience: str | None = Field(default=None, max_length=300)
    language: str = Field(default="en", max_length=16)
    tone: str = Field(default="engaging", max_length=60)
    video_format: str = Field(default="documentary", max_length=60)
    target_duration_minutes: int = Field(default=10, ge=1, le=180)
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    visual_style: str = Field(default="cinematic", max_length=100)
    settings: ProjectSettings | None = None

    @field_validator("aspect_ratio")
    @classmethod
    def _ar(cls, v: str) -> str:
        if v not in ASPECT_RATIOS:
            raise ValueError(f"aspect_ratio must be one of {ASPECT_RATIOS}")
        return v

    @field_validator("resolution")
    @classmethod
    def _res(cls, v: str) -> str:
        if v not in RESOLUTIONS:
            raise ValueError(f"resolution must be one of {RESOLUTIONS}")
        return v


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    topic: str | None = Field(default=None, min_length=3, max_length=4000)
    description: str | None = None
    niche: str | None = None
    target_audience: str | None = None
    language: str | None = None
    tone: str | None = None
    video_format: str | None = None
    target_duration_minutes: int | None = Field(default=None, ge=1, le=180)
    aspect_ratio: str | None = None
    resolution: str | None = None
    visual_style: str | None = None
    status: ProjectStatus | None = None
    settings: dict[str, Any] | None = None


class ProjectSummary(ORMModel):
    id: uuid.UUID
    title: str
    topic: str
    niche: str | None
    language: str
    tone: str
    video_format: str
    target_duration_minutes: int
    aspect_ratio: str
    resolution: str
    visual_style: str
    status: ProjectStatus
    thumbnail_url: str | None = None
    final_video_url: str | None = None
    estimated_duration_seconds: float | None
    created_at: datetime
    updated_at: datetime
    active_job: dict[str, Any] | None = None


class ProjectDetail(ProjectSummary):
    description: str | None
    target_audience: str | None
    settings: dict[str, Any]
    thumbnail_asset_id: uuid.UUID | None
    final_video_asset_id: uuid.UUID | None
    last_opened_at: datetime | None
    counts: dict[str, int] = Field(default_factory=dict)
    pipeline: dict[str, bool] = Field(default_factory=dict)


class ProjectStats(BaseModel):
    total: int
    drafts: int
    generating: int
    completed: int
    failed: int
