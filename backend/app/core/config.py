"""Application configuration.

Every secret and environment-specific value is read from environment variables
(or a `.env` file in development). Nothing here is ever shipped to the browser.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App -------------------------------------------------------------
    app_name: str = "LongForm AI"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_origin_regex: str | None = None  # e.g. r"https://.*\.yourdomain\.com" or a preview-host pattern
    log_level: str = "INFO"

    # --- Security --------------------------------------------------------
    secret_key: str = "change-me-in-production-please-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_generation: str = "30/minute"

    # --- Database --------------------------------------------------------
    database_url: str = "postgresql+asyncpg://longform:longform@localhost:5432/longform"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # --- Redis / queue ---------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    job_default_timeout_seconds: int = 60 * 30
    render_job_timeout_seconds: int = 60 * 60 * 2
    job_max_retries: int = 3
    worker_heartbeat_ttl_seconds: int = 60

    # --- Storage ---------------------------------------------------------
    storage_backend: Literal["s3", "local"] = "local"
    storage_local_path: str = str(REPO_ROOT / "data" / "storage")
    storage_public_base_url: str | None = None  # e.g. CDN in front of the bucket
    s3_endpoint_url: str | None = None  # MinIO / R2 / etc.
    s3_region: str = "us-east-1"
    s3_bucket: str = "longform-media"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_use_path_style: bool = True
    signed_url_expire_seconds: int = 60 * 60

    # --- Providers -------------------------------------------------------
    llm_provider: str = "mock"  # mock | openai | anthropic | openai_compatible
    image_provider: str = "mock"  # mock | openai | stability | replicate
    video_provider: str = "mock"  # mock | replicate | runway | luma
    tts_provider: str = "mock"  # mock | openai | elevenlabs | azure
    stt_provider: str = "mock"  # mock | openai_whisper | deepgram
    stock_provider: str = "mock"  # mock | pexels | pixabay

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_llm_model: str = "gpt-4o-mini"
    openai_image_model: str = "gpt-image-1"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_stt_model: str = "whisper-1"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"

    elevenlabs_api_key: str | None = None
    elevenlabs_model_id: str = "eleven_multilingual_v2"

    stability_api_key: str | None = None
    replicate_api_token: str | None = None
    replicate_image_model: str = "black-forest-labs/flux-schnell"
    replicate_video_model: str = "minimax/video-01"
    runway_api_key: str | None = None
    luma_api_key: str | None = None
    deepgram_api_key: str | None = None
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None

    provider_timeout_seconds: int = 120
    provider_max_retries: int = 3

    # --- Rendering -------------------------------------------------------
    ffmpeg_binary: str | None = None  # auto-detected when unset
    ffprobe_binary: str | None = None
    render_threads: int = 0  # 0 = ffmpeg auto
    render_preset: str = "medium"
    render_crf: int = 20
    render_work_dir: str = str(REPO_ROOT / "data" / "work")
    font_path: str | None = None
    watermark_text: str = "Made with LongForm AI"
    max_video_duration_minutes: int = 120

    # --- Billing ---------------------------------------------------------
    free_plan_credits: int = 500
    credit_cost_research: int = 5
    credit_cost_script_per_minute: int = 2
    credit_cost_tts_per_1k_chars: int = 3
    credit_cost_image: int = 4
    credit_cost_video_clip: int = 25
    credit_cost_render_per_minute: int = 6
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_creator: str | None = None
    stripe_price_pro: str | None = None
    stripe_price_studio: str | None = None
    stripe_price_credits: str | None = None  # one-time price for a 100-credit pack

    # --- Uploads -----------------------------------------------------------
    max_direct_upload_bytes: int = 200 * 1024 * 1024  # larger files go through presigned PUT

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def sync_database_url(self) -> str:
        """Driver-agnostic sync URL for Alembic and Celery workers."""
        url = self.database_url
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        url = url.replace("sqlite+aiosqlite://", "sqlite://")
        return url

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
