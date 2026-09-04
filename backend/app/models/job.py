from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import JobState, JobType

if TYPE_CHECKING:
    from app.models.project import Project


class JobMixin(UUIDPrimaryKeyMixin, TimestampMixin):
    """Fields shared by generation and render jobs."""

    state: Mapped[JobState] = mapped_column(
        Enum(JobState, name="job_state", native_enum=False, length=32),
        default=JobState.QUEUED,
        nullable=False,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(120))
    message: Mapped[str | None] = mapped_column(String(500))
    # Idempotency: the same key for the same user is only ever executed once
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    worker_id: Mapped[str | None] = mapped_column(String(120))
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    logs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    eta_seconds: Mapped[int | None] = mapped_column(Integer)
    credits_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GenerationJob(JobMixin, Base):
    """Any AI generation task: research, script, scenes, voiceover, visuals, captions, full pipeline."""

    __tablename__ = "generation_jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, name="job_type", native_enum=False, length=32), nullable=False
    )
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("generation_jobs.id", ondelete="SET NULL")
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))  # scene / section id

    project: Mapped[Project] = relationship(back_populates="generation_jobs")

    __table_args__ = (
        Index("ix_generation_jobs_project_id_created_at", "project_id", "created_at"),
        Index("ix_generation_jobs_user_id_state", "user_id", "state"),
        Index("ix_generation_jobs_state_queued_at", "state", "queued_at"),
        Index("uq_generation_jobs_idempotency", "user_id", "idempotency_key", unique=True, postgresql_where=text("idempotency_key IS NOT NULL")),
    )


class RenderJob(JobMixin, Base):
    """FFmpeg composition job producing a preview or final MP4."""

    __tablename__ = "render_jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=1920, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    format: Mapped[str] = mapped_column(String(16), default="mp4", nullable=False)
    burn_captions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_watermark: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timeline_version: Mapped[int | None] = mapped_column(Integer)
    timeline_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    output_duration_seconds: Mapped[float | None] = mapped_column(Float)
    output_size_bytes: Mapped[int | None] = mapped_column(Integer)
    render_seconds: Mapped[float | None] = mapped_column(Float)

    project: Mapped[Project] = relationship(back_populates="render_jobs")

    __table_args__ = (
        Index("ix_render_jobs_project_id_created_at", "project_id", "created_at"),
        Index("ix_render_jobs_user_id_state", "user_id", "state"),
        Index("uq_render_jobs_idempotency", "user_id", "idempotency_key", unique=True, postgresql_where=text("idempotency_key IS NOT NULL")),
    )


class WorkerHeartbeat(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Health record refreshed by each worker process; used by /health/workers."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(200), nullable=False)
    queues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[str | None] = mapped_column(String(40))
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
