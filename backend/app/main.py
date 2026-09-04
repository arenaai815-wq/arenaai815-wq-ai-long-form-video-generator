"""FastAPI application factory.

The web process only ever does light work: auth, CRUD, enqueueing jobs and relaying
progress events. Every AI call and every FFmpeg invocation runs in Celery workers.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.api.deps import limiter
from app.api.v1 import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger("app")

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness, worker and queue health."},
    {"name": "auth", "description": "Signup, login, refresh-token rotation, sessions and API keys."},
    {"name": "projects", "description": "Video projects: settings, pipeline runs and statistics."},
    {"name": "research", "description": "AI research: facts, statistics and sources grouped into sections."},
    {"name": "scripts", "description": "AI scripts with versioning and per-section regeneration."},
    {"name": "scenes", "description": "Storyboard: scenes, prompts and visual generation."},
    {"name": "voiceovers", "description": "Text-to-speech voices and per-scene narration."},
    {"name": "captions", "description": "SRT/VTT captions and styling."},
    {"name": "timeline", "description": "Multi-track timeline document and edit operations."},
    {"name": "rendering", "description": "Preview/final FFmpeg renders and MP4 export."},
    {"name": "jobs", "description": "Background jobs, cancellation, retries and SSE progress streams."},
    {"name": "media", "description": "Media library, uploads, stock footage and music."},
    {"name": "usage", "description": "Usage metering and the credit ledger."},
    {"name": "billing", "description": "Plans, subscriptions, Stripe checkout and webhooks."},
    {"name": "providers", "description": "AI provider catalogue and health."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api starting", environment=settings.environment, storage=settings.storage_backend)
    if settings.is_production and settings.secret_key.startswith("change-me"):
        raise RuntimeError("SECRET_KEY must be set in production")
    yield
    from app.db.session import async_engine

    await async_engine.dispose()
    log.info("api stopped")


def _error_payload(code: str, message: str, details: Any = None, request_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    if request_id:
        body["error"]["request_id"] = request_id
    return body


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0",
        description=(
            "REST API for the AI long-form video production platform. "
            "Authenticate with `Authorization: Bearer <access_token>` or `X-API-Key`. "
            "Long-running work returns a job (HTTP 202); follow progress on `/jobs/{id}/events` (SSE)."
        ),
        openapi_tags=OPENAPI_TAGS,
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        lifespan=lifespan,
    )

    # --- middleware ---------------------------------------------------------------------
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path, method=request.method)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error")
            return JSONResponse(status_code=500, content=_error_payload("internal_error", "Internal server error", request_id=request_id))
        response.headers["X-Request-ID"] = request_id
        if not settings.is_production:
            response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    # --- exception handlers ------------------------------------------------------------
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_error_payload(exc.code, exc.message, exc.details))

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        resp = JSONResponse(status_code=429, content=_error_payload("rate_limited", f"Rate limit exceeded: {exc.detail}"))
        try:
            return request.app.state.limiter._inject_headers(resp, request.state.view_rate_limit)
        except Exception:
            return resp

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = [{"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse(status_code=422, content=_error_payload("validation_error", "Request validation failed", {"errors": errors}))

    # --- routes --------------------------------------------------------------------------
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": f"{settings.api_v1_prefix}/docs", "health": f"{settings.api_v1_prefix}/health"}

    return app


app = create_app()
