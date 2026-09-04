"""Pydantic mirror of shared/schemas/timeline.json."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

TrackKind = Literal["video", "image", "voiceover", "music", "sfx", "text", "captions"]
TransitionType = Literal[
    "none", "fade", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright",
    "circleopen", "fadeblack", "fadewhite", "smoothleft", "smoothright",
]
MotionType = Literal["none", "ken_burns", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]
TextPosition = Literal["top", "center", "bottom", "top_left", "top_right", "bottom_left", "bottom_right"]


class Transition(BaseModel):
    type: TransitionType = "fade"
    duration: float = Field(default=0.5, ge=0, le=5)


class MotionEffect(BaseModel):
    type: MotionType = "ken_burns"
    intensity: float = Field(default=0.1, ge=0, le=1)


class TextOverlay(BaseModel):
    content: str = ""
    font_family: str = "DejaVu Sans"
    font_size: int = Field(default=56, ge=8, le=300)
    color: str = "#FFFFFF"
    background: str | None = None
    position: TextPosition = "center"
    animation: Literal["none", "fade", "slide_up", "typewriter"] = "fade"


class Clip(BaseModel):
    id: str
    scene_id: str | None = None
    asset_id: str | None = None
    asset_kind: Literal["image", "video", "audio", "voiceover", "text"] | None = None
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    trim_start: float = Field(default=0, ge=0)
    trim_end: float = Field(default=0, ge=0)
    volume: float = Field(default=1.0, ge=0, le=3)
    fade_in: float = Field(default=0, ge=0)
    fade_out: float = Field(default=0, ge=0)
    transition_in: Transition | None = None
    effect: MotionEffect | None = None
    text: TextOverlay | None = None
    label: str | None = None
    src_url: str | None = None  # populated on read for the browser preview

    @property
    def end(self) -> float:
        return self.start + self.duration


class Track(BaseModel):
    id: str
    kind: TrackKind
    name: str = ""
    muted: bool = False
    locked: bool = False
    volume: float = Field(default=1.0, ge=0, le=3)
    clips: list[Clip] = Field(default_factory=list)


class CaptionSettingsDoc(BaseModel):
    enabled: bool = True
    burn_in: bool = True
    font_family: str = "DejaVu Sans"
    font_size: int = 44
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: float = 2
    background_color: str | None = None
    position: Literal["top", "center", "bottom"] = "bottom"
    margin_v: int = 60
    animation: Literal["none", "fade", "pop", "karaoke"] = "none"
    max_chars_per_line: int = 42
    max_lines: int = 2
    timing_offset: float = 0.0
    highlight_color: str = "#FFD400"


class WatermarkDoc(BaseModel):
    enabled: bool = False
    asset_id: str | None = None
    text: str | None = None
    position: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "bottom_right"
    opacity: float = Field(default=0.6, ge=0, le=1)


class TimelineDocument(BaseModel):
    version: int = 1
    fps: int = 30
    width: int = 1920
    height: int = 1080
    duration: float = 0
    background_color: str = "#000000"
    tracks: list[Track] = Field(default_factory=list)
    captions: CaptionSettingsDoc = Field(default_factory=CaptionSettingsDoc)
    watermark: WatermarkDoc = Field(default_factory=WatermarkDoc)

    def compute_duration(self) -> float:
        end = 0.0
        for t in self.tracks:
            for c in t.clips:
                end = max(end, c.start + c.duration)
        return round(end, 3)


class TimelinePublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    fps: int
    width: int
    height: int
    duration_seconds: float
    data: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TimelineSaveRequest(BaseModel):
    data: TimelineDocument
    base_version: int | None = None  # optimistic concurrency


class TimelineOpsRequest(BaseModel):
    """Small server-side edit operations that keep scenes and timeline consistent."""

    op: Literal["reorder_scenes", "trim_clip", "split_clip", "set_volume", "set_fade", "move_clip", "delete_clip", "set_transition", "set_effect"]
    payload: dict[str, Any] = Field(default_factory=dict)
