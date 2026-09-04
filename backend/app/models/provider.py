from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProviderKind


class AIProvider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Registry + health/usage stats for configured AI providers.

    Credentials are *never* stored here; they come from environment variables.
    This table lets operators enable/disable providers, set priorities and view health.
    """

    __tablename__ = "ai_providers"

    kind: Mapped[ProviderKind] = mapped_column(
        Enum(ProviderKind, name="provider_kind", native_enum=False, length=16), nullable=False
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. "openai", "elevenlabs", "mock"
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    default_model: Mapped[str | None] = mapped_column(String(120))
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # non-secret config
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_ai_providers_kind_name"),
        Index("ix_ai_providers_kind_enabled", "kind", "is_enabled"),
    )
