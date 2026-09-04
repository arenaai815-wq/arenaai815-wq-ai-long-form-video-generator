from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import JobState, JobType
from app.schemas.common import ORMModel


class JobPublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    job_type: JobType | str
    state: JobState
    progress: int
    stage: str | None
    message: str | None
    attempt: int
    max_attempts: int
    cancel_requested: bool
    params: dict[str, Any]
    result: dict[str, Any]
    error: str | None
    eta_seconds: int | None
    credits_reserved: int
    credits_charged: int
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    kind: str = "generation"  # generation | render
    logs: list[Any] = Field(default_factory=list)


class RenderJobPublic(JobPublic):
    is_preview: bool
    width: int
    height: int
    fps: int
    format: str
    burn_captions: bool
    include_watermark: bool
    output_asset_id: uuid.UUID | None
    output_duration_seconds: float | None
    output_size_bytes: int | None
    render_seconds: float | None
    output_url: str | None = None
    kind: str = "render"
    job_type: JobType | str = "render"


class PipelineRequest(BaseModel):
    """Run the full topic -> MP4 pipeline (or a subset of stages)."""

    stages: list[str] = Field(
        default_factory=lambda: ["research", "script", "scenes", "voiceover", "visuals", "captions", "render"]
    )
    skip_existing: bool = True
    render_preview: bool = False
    options: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Optional per-stage options keyed by stage name, e.g. "
            '{"research": {"section_count": 6, "depth": "deep"}, "voiceover": {"voice_id": "...", "speed": 1.05}, '
            '"visuals": {"visual_type": "ai_image", "provider": "openai"}}. Same fields as the individual stage endpoints.'
        ),
    )
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("stages")
    @classmethod
    def _known_stages(cls, v: list[str]) -> list[str]:
        known = ["research", "script", "scenes", "voiceover", "visuals", "captions", "render"]
        bad = [s for s in v if s not in known]
        if bad:
            raise ValueError(f"unknown stage(s): {', '.join(bad)}; valid: {', '.join(known)}")
        # keep pipeline order regardless of how the client listed them
        return [s for s in known if s in v]

    @field_validator("options")
    @classmethod
    def _known_option_keys(cls, v: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        known = {"research", "script", "scenes", "voiceover", "visuals", "captions"}
        bad = sorted(set(v) - known)
        if bad:
            raise ValueError(f"options for unknown stage(s): {', '.join(bad)}")
        return v


class RenderRequest(BaseModel):
    preview: bool = False
    resolution: str | None = None
    fps: int | None = Field(default=None, ge=15, le=60)
    burn_captions: bool | None = None
    include_watermark: bool | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    range_start: float | None = Field(default=None, ge=0)  # preview a segment
    range_end: float | None = Field(default=None, gt=0)


class JobProgressEvent(BaseModel):
    job_id: str
    project_id: str
    job_type: str
    state: str
    stage: str
    progress: int
    message: str
    eta_seconds: int | None
    result: dict[str, Any] | None
    error: str | None
    ts: str


class WorkerStatus(BaseModel):
    worker_id: str
    hostname: str
    queues: list[str]
    concurrency: int
    active_tasks: int
    processed_total: int
    failed_total: int
    last_heartbeat_at: datetime
    healthy: bool
    version: str | None


class QueueStats(BaseModel):
    queued: int
    processing: int
    completed_24h: int
    failed_24h: int
    workers_online: int
    queue_depths: dict[str, int]
