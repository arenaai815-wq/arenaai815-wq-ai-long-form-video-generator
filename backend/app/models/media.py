from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AudioKind, MediaKind, MediaSource

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Any visual/binary object in object storage. Files themselves never live in Postgres."""

    __tablename__ = "media_assets"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    kind: Mapped[MediaKind] = mapped_column(
        Enum(MediaKind, name="media_kind", native_enum=False, length=16), nullable=False
    )
    source: Mapped[MediaSource] = mapped_column(
        Enum(MediaSource, name="media_source", native_enum=False, length=16), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(1024))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    fps: Mapped[float | None] = mapped_column(Float)
    checksum: Mapped[str | None] = mapped_column(String(128))
    prompt: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(60))
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_reusable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_uploaded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    owner: Mapped[User] = relationship(back_populates="media_assets")
    project: Mapped[Project | None] = relationship(back_populates="media_assets")

    __table_args__ = (
        Index("ix_media_assets_owner_id_kind", "owner_id", "kind"),
        Index("ix_media_assets_project_id_kind", "project_id", "kind"),
        Index("ix_media_assets_scene_id", "scene_id"),
    )


class AudioAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Music beds, sound effects and raw voice recordings."""

    __tablename__ = "audio_assets"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    kind: Mapped[AudioKind] = mapped_column(
        Enum(AudioKind, name="audio_kind", native_enum=False, length=16), nullable=False
    )
    source: Mapped[MediaSource] = mapped_column(
        Enum(MediaSource, name="media_source", native_enum=False, length=16),
        default=MediaSource.UPLOAD,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    mood: Mapped[str | None] = mapped_column(String(60))
    bpm: Mapped[int | None] = mapped_column(Integer)
    license: Mapped[str | None] = mapped_column(String(120))
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    owner: Mapped[User] = relationship(back_populates="audio_assets")
    project: Mapped[Project | None] = relationship(back_populates="audio_assets")

    __table_args__ = (Index("ix_audio_assets_owner_id_kind", "owner_id", "kind"),)


class Voiceover(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-scene narration audio produced by a TTS provider."""

    __tablename__ = "voiceovers"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(120), nullable=False)
    voice_name: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    style: Mapped[str | None] = mapped_column(String(60))
    speed: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(120), default="audio/mpeg", nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    # Word-level timings [{"word","start","end"}] - used for caption alignment
    word_timings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    project: Mapped[Project] = relationship(back_populates="voiceovers")

    __table_args__ = (
        Index("ix_voiceovers_project_id_scene_id", "project_id", "scene_id"),
        Index("ix_voiceovers_text_hash_voice", "text_hash", "voice_id", "provider"),
    )


class Caption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Subtitle cues for a project (whole-video timeline) plus rendering style."""

    __tablename__ = "captions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    # [{"index", "start", "end", "text", "scene_id", "words": [{"word","start","end"}]}]
    cues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    style: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    srt_storage_key: Mapped[str | None] = mapped_column(String(1024))
    vtt_storage_key: Mapped[str | None] = mapped_column(String(1024))
    source: Mapped[str] = mapped_column(String(32), default="tts_timings", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(60))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project: Mapped[Project] = relationship(back_populates="captions")

    __table_args__ = (Index("ix_captions_project_id_is_current", "project_id", "is_current"),)
