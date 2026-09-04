from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProjectStatus

if TYPE_CHECKING:
    from app.models.job import GenerationJob, RenderJob
    from app.models.media import AudioAsset, Caption, MediaAsset, Voiceover
    from app.models.scene import Scene
    from app.models.script import Script
    from app.models.timeline import Timeline
    from app.models.user import User


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    niche: Mapped[str | None] = mapped_column(String(100))
    target_audience: Mapped[str | None] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    tone: Mapped[str] = mapped_column(String(60), default="engaging", nullable=False)
    video_format: Mapped[str] = mapped_column(String(60), default="documentary", nullable=False)
    target_duration_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="16:9", nullable=False)
    resolution: Mapped[str] = mapped_column(String(10), default="1080p", nullable=False)
    visual_style: Mapped[str] = mapped_column(String(100), default="cinematic", nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status", native_enum=False, length=32),
        default=ProjectStatus.DRAFT,
        nullable=False,
    )
    # Per-project generation settings (voice, music, captions, watermark...)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    thumbnail_asset_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    final_video_asset_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    estimated_duration_seconds: Mapped[float | None] = mapped_column(Float)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="projects")
    research: Mapped[Research | None] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    scripts: Mapped[list[Script]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Script.version.desc()"
    )
    scenes: Mapped[list[Scene]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Scene.order_index"
    )
    media_assets: Mapped[list[MediaAsset]] = relationship(back_populates="project")
    audio_assets: Mapped[list[AudioAsset]] = relationship(back_populates="project")
    voiceovers: Mapped[list[Voiceover]] = relationship(back_populates="project", cascade="all, delete-orphan")
    captions: Mapped[list[Caption]] = relationship(back_populates="project", cascade="all, delete-orphan")
    timeline: Mapped[Timeline | None] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    generation_jobs: Mapped[list[GenerationJob]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    render_jobs: Mapped[list[RenderJob]] = relationship(back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_projects_owner_id_updated_at", "owner_id", "updated_at"),
        Index("ix_projects_owner_id_status", "owner_id", "status"),
    )


class Research(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """AI research pack for a project. `sections` is structured so the scriptwriter can consume it."""

    __tablename__ = "research"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    # [{"title": str, "key_points": [str], "facts": [str], "statistics": [{"value","context","source"}], "sources": [{"title","url","note"}]}]
    sections: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    key_facts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    statistics: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    suggested_angles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="research")
