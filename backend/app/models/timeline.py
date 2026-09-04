from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project


class Timeline(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The editable multi-track timeline. `data` follows shared/schemas/timeline.json."""

    __tablename__ = "timelines"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=1920, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Undo history is client-side; server keeps a small number of snapshots for recovery
    snapshots: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64))

    project: Mapped[Project] = relationship(back_populates="timeline")
