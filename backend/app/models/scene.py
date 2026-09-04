from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import VisualType

if TYPE_CHECKING:
    from app.models.media import MediaAsset, Voiceover
    from app.models.project import Project
    from app.models.script import ScriptSection


class Scene(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A storyboard unit: one narration chunk + one visual + timing metadata."""

    __tablename__ = "scenes"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("script_sections.id", ondelete="SET NULL")
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    narration: Mapped[str] = mapped_column(Text, default="", nullable=False)
    visual_description: Mapped[str | None] = mapped_column(Text)
    suggested_footage: Mapped[str | None] = mapped_column(Text)
    image_prompt: Mapped[str | None] = mapped_column(Text)
    video_prompt: Mapped[str | None] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    on_screen_text: Mapped[str | None] = mapped_column(String(300))
    visual_type: Mapped[VisualType] = mapped_column(
        Enum(VisualType, name="visual_type", native_enum=False, length=32),
        default=VisualType.AI_IMAGE,
        nullable=False,
    )
    duration_seconds: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    transition: Mapped[str] = mapped_column(String(40), default="fade", nullable=False)
    transition_duration: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    motion_effect: Mapped[str] = mapped_column(String(40), default="ken_burns", nullable=False)
    music_suggestion: Mapped[str | None] = mapped_column(String(200))
    music_mood: Mapped[str | None] = mapped_column(String(60))
    sound_effects: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    visual_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    voiceover_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("voiceovers.id", ondelete="SET NULL", use_alter=True)
    )
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    project: Mapped[Project] = relationship(back_populates="scenes")
    section: Mapped[ScriptSection | None] = relationship(back_populates="scenes")
    visual_asset: Mapped[MediaAsset | None] = relationship(foreign_keys=[visual_asset_id])
    voiceover: Mapped[Voiceover | None] = relationship(
        foreign_keys=[voiceover_id], post_update=True
    )

    __table_args__ = (Index("ix_scenes_project_id_order", "project_id", "order_index"),)
