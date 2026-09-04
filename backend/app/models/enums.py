"""Enumerations shared across models, schemas and workers.

`JobState` mirrors shared/schemas/job_states.json - keep in sync.
"""

from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:  # pragma: no cover
        return str(self.value)


class JobState(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    RESEARCHING = "RESEARCHING"
    GENERATING_SCRIPT = "GENERATING_SCRIPT"
    GENERATING_SCENES = "GENERATING_SCENES"
    GENERATING_AUDIO = "GENERATING_AUDIO"
    GENERATING_VISUALS = "GENERATING_VISUALS"
    GENERATING_CAPTIONS = "GENERATING_CAPTIONS"
    RENDERING = "RENDERING"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATES


TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED})

# Share of a full pipeline run each stage consumes (mirrors job_states.json)
STAGE_WEIGHTS: dict[JobState, float] = {
    JobState.RESEARCHING: 0.08,
    JobState.GENERATING_SCRIPT: 0.12,
    JobState.GENERATING_SCENES: 0.05,
    JobState.GENERATING_AUDIO: 0.20,
    JobState.GENERATING_VISUALS: 0.25,
    JobState.GENERATING_CAPTIONS: 0.05,
    JobState.RENDERING: 0.22,
    JobState.UPLOADING: 0.03,
}


class JobType(StrEnum):
    RESEARCH = "research"
    SCRIPT = "script"
    SCRIPT_SECTION = "script_section"
    SCENES = "scenes"
    VOICEOVER = "voiceover"
    VISUALS = "visuals"
    CAPTIONS = "captions"
    FULL_PIPELINE = "full_pipeline"
    RENDER = "render"
    PREVIEW_RENDER = "preview_render"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    RESEARCHING = "researching"
    SCRIPTING = "scripting"
    STORYBOARDING = "storyboarding"
    GENERATING = "generating"
    EDITING = "editing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class AspectRatio(StrEnum):
    WIDESCREEN = "16:9"
    VERTICAL = "9:16"
    SQUARE = "1:1"
    CLASSIC = "4:3"


class Resolution(StrEnum):
    HD = "720p"
    FULL_HD = "1080p"
    QHD = "1440p"
    UHD = "4k"


RESOLUTION_DIMENSIONS: dict[tuple[str, str], tuple[int, int]] = {
    ("16:9", "720p"): (1280, 720),
    ("16:9", "1080p"): (1920, 1080),
    ("16:9", "1440p"): (2560, 1440),
    ("16:9", "4k"): (3840, 2160),
    ("9:16", "720p"): (720, 1280),
    ("9:16", "1080p"): (1080, 1920),
    ("9:16", "1440p"): (1440, 2560),
    ("9:16", "4k"): (2160, 3840),
    ("1:1", "720p"): (720, 720),
    ("1:1", "1080p"): (1080, 1080),
    ("1:1", "1440p"): (1440, 1440),
    ("1:1", "4k"): (2160, 2160),
    ("4:3", "720p"): (960, 720),
    ("4:3", "1080p"): (1440, 1080),
    ("4:3", "1440p"): (1920, 1440),
    ("4:3", "4k"): (2880, 2160),
}


def dimensions_for(aspect_ratio: str, resolution: str) -> tuple[int, int]:
    return RESOLUTION_DIMENSIONS.get((aspect_ratio, resolution), (1920, 1080))


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FONT = "font"
    SUBTITLE = "subtitle"
    OTHER = "other"


class MediaSource(StrEnum):
    UPLOAD = "upload"
    AI_IMAGE = "ai_image"
    AI_VIDEO = "ai_video"
    STOCK = "stock"
    RENDER = "render"
    SYSTEM = "system"


class AudioKind(StrEnum):
    VOICEOVER = "voiceover"
    MUSIC = "music"
    SFX = "sfx"


class SectionKind(StrEnum):
    HOOK = "hook"
    INTRO = "intro"
    BODY = "body"
    TRANSITION = "transition"
    STORY = "story"
    CONCLUSION = "conclusion"
    CTA = "cta"


class VisualType(StrEnum):
    AI_IMAGE = "ai_image"
    AI_VIDEO = "ai_video"
    STOCK_VIDEO = "stock_video"
    STOCK_IMAGE = "stock_image"
    UPLOAD = "upload"
    TEXT_CARD = "text_card"


class ProviderKind(StrEnum):
    LLM = "llm"
    IMAGE = "image"
    VIDEO = "video"
    TTS = "tts"
    STT = "stt"
    STOCK = "stock"


class PlanTier(StrEnum):
    FREE = "free"
    CREATOR = "creator"
    PRO = "pro"
    STUDIO = "studio"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class UsageKind(StrEnum):
    LLM_TOKENS = "llm_tokens"
    RESEARCH = "research"
    SCRIPT = "script"
    TTS_CHARACTERS = "tts_characters"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    STT_SECONDS = "stt_seconds"
    RENDER_SECONDS = "render_seconds"
    STORAGE_BYTES = "storage_bytes"


class CreditTransactionKind(StrEnum):
    GRANT = "grant"
    PURCHASE = "purchase"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    CONSUMPTION = "consumption"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"
