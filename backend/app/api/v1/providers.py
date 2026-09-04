"""AI provider catalogue & health (never exposes secrets)."""

from __future__ import annotations

import time
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, require_superuser
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.enums import ProviderKind
from app.models.provider import AIProvider
from app.models.user import User
from app.providers import get_registry

router = APIRouter()


@router.get("", summary="Available adapters per capability and which one is active")
async def list_providers(user: CurrentUser) -> dict[str, Any]:
    reg = get_registry()
    available = reg.available()
    return {
        "active": reg.active(),
        "available": {kind: [info.__dict__ for info in infos] for kind, infos in available.items()},
        "configured_from": {
            "llm": settings.llm_provider, "image": settings.image_provider, "video": settings.video_provider,
            "tts": settings.tts_provider, "stt": settings.stt_provider, "stock": settings.stock_provider,
        },
    }


@router.get("/health", summary="Ping every active provider (admin)")
async def providers_health(admin: Annotated[User, Depends(require_superuser)]) -> dict[str, Any]:
    reg = get_registry()
    out: dict[str, Any] = {}
    for kind in ("llm", "image", "video", "tts", "stt", "stock"):
        p = reg.get(kind)
        t0 = time.perf_counter()
        try:
            ok = await anyio.to_thread.run_sync(p.health_check)
            err = None
        except Exception as exc:  # pragma: no cover - network dependent
            ok, err = False, str(exc)[:200]
        out[kind] = {"provider": p.name, "is_mock": p.is_mock, "healthy": bool(ok), "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "error": err}
    return out


@router.get("/stats", summary="Persisted provider usage statistics (admin)")
async def provider_stats(admin: Annotated[User, Depends(require_superuser)], db: DB) -> list[dict[str, Any]]:
    rows = (await db.execute(select(AIProvider).order_by(AIProvider.kind, AIProvider.priority))).scalars().all()
    return [
        {
            "id": str(r.id), "kind": r.kind.value, "name": r.name, "display_name": r.display_name, "is_enabled": r.is_enabled,
            "is_default": r.is_default, "is_configured": r.is_configured, "default_model": r.default_model,
            "total_requests": r.total_requests, "total_failures": r.total_failures, "avg_latency_ms": r.avg_latency_ms,
            "last_success_at": r.last_success_at, "last_failure_at": r.last_failure_at, "capabilities": r.capabilities,
        }
        for r in rows
    ]


@router.post("/sync", summary="Sync the adapter catalogue into the ai_providers table (admin)")
async def sync_provider_catalogue(admin: Annotated[User, Depends(require_superuser)], db: DB) -> dict[str, int]:
    reg = get_registry()
    n = 0
    for kind, infos in reg.available().items():
        for info in infos:
            row = (await db.execute(select(AIProvider).where(AIProvider.kind == ProviderKind(kind), AIProvider.name == info.name))).scalar_one_or_none()
            if row is None:
                row = AIProvider(kind=ProviderKind(kind), name=info.name, display_name=info.display_name)
                db.add(row)
            row.is_configured = info.is_configured
            row.default_model = info.default_model
            row.capabilities = {k: v for k, v in info.capabilities.items() if k != "active"}
            row.is_default = bool(info.capabilities.get("active"))
            n += 1
    return {"synced": n}


@router.get("/{kind}/models", summary="Models offered by the active adapter of a capability")
async def provider_models(kind: str, user: CurrentUser) -> dict[str, Any]:
    if kind not in ("llm", "image", "video", "tts", "stt", "stock"):
        raise NotFoundError("Unknown provider kind")
    p = get_registry().get(kind)
    models = await anyio.to_thread.run_sync(p.list_models) if hasattr(p, "list_models") else []
    return {"kind": kind, "provider": p.name, "default_model": getattr(p, "model", None), "models": models}
