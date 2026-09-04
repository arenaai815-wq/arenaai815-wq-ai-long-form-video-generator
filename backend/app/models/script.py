from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SectionKind

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.scene import Scene


class Script(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A versioned script. Only one version per project is `is_current`."""

    __tablename__ = "scripts"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    hook: Mapped[str | None] = mapped_column(Text)
    outline: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_duration_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    target_duration_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    words_per_minute: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="scripts")
    sections: Mapped[list[ScriptSection]] = relationship(
        back_populates="script", cascade="all, delete-orphan", order_by="ScriptSection.order_index"
    )

    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_scripts_project_version"),
        Index("ix_scripts_project_id_is_current", "project_id", "is_current"),
    )


class ScriptSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "script_sections"

    script_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[SectionKind] = mapped_column(
        Enum(SectionKind, name="section_kind", native_enum=False, length=32),
        default=SectionKind.BODY,
        nullable=False,
    )
    heading: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    talking_points: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_duration_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    regeneration_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    script: Mapped[Script] = relationship(back_populates="sections")
    scenes: Mapped[list[Scene]] = relationship(back_populates="section")

    __table_args__ = (Index("ix_script_sections_script_id_order", "script_id", "order_index"),)
