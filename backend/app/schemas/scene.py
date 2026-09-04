from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import VisualType
from app.schemas.common import ORMModel


class ScenePublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    section_id: uuid.UUID | None
    order_index: int
    title: str | None
    narration: str
    visual_description: str | None
    suggested_footage: str | None
    image_prompt: str | None
    video_prompt: str | None
    negative_prompt: str | None
    on_screen_text: str | None
    visual_type: VisualType
    duration_seconds: float
    transition: str
    transition_duration: float
    motion_effect: str
    music_suggestion: str | None
    music_mood: str | None
    sound_effects: list[Any]
    keywords: list[Any]
    visual_asset_id: uuid.UUID | None
    voiceover_id: uuid.UUID | None
    status: str
    extra: dict[str, Any]
    updated_at: datetime
    # Denormalised for the storyboard UI
    visual_url: str | None = None
    visual_thumbnail_url: str | None = None
    visual_kind: str | None = None
    voiceover_url: str | None = None
    voiceover_duration: float | None = None
    voiceover_status: str | None = None
    start_time: float | None = None


class SceneUpdate(BaseModel):
    title: str | None = None
    narration: str | None = None
    visual_description: str | None = None
    suggested_footage: str | None = None
    image_prompt: str | None = None
    video_prompt: str | None = None
    negative_prompt: str | None = None
    on_screen_text: str | None = None
    visual_type: VisualType | None = None
    duration_seconds: float | None = Field(default=None, ge=0.5, le=600)
    transition: str | None = None
    transition_duration: float | None = Field(default=None, ge=0, le=5)
    motion_effect: str | None = None
    music_suggestion: str | None = None
    music_mood: str | None = None
    sound_effects: list[str] | None = None
    keywords: list[str] | None = None
    visual_asset_id: uuid.UUID | None = None
    extra: dict[str, Any] | None = None


class SceneCreate(BaseModel):
    narration: str = ""
    title: str | None = None
    after_scene_id: uuid.UUID | None = None
    visual_type: VisualType = VisualType.AI_IMAGE
    image_prompt: str | None = None
    duration_seconds: float = 8.0


class SceneReorder(BaseModel):
    scene_ids: list[uuid.UUID]


class SceneSplitRequest(BaseModel):
    at_character: int = Field(ge=1)


class ScenesGenerateRequest(BaseModel):
    scene_target_seconds: float | None = Field(default=None, ge=4, le=30)
    regenerate_prompts_only: bool = False


class VisualGenerateRequest(BaseModel):
    scene_ids: list[uuid.UUID] | None = None  # None = all scenes missing visuals
    force: bool = False  # regenerate even if a visual exists
    visual_type: VisualType | None = None  # override per request
    provider: str | None = None
    prompt_override: str | None = None


class SceneVisualFromAsset(BaseModel):
    asset_id: uuid.UUID


class SceneVisualFromStock(BaseModel):
    item_id: str
    kind: str = "video"
    download_url: str
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    source: str = "pexels"
