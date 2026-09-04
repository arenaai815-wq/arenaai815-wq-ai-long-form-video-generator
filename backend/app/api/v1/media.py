"""Media library: uploads (presigned), assets, audio/music library, stock search, signed local file serving."""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentUser, limiter
from app.core.config import settings
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.enums import AudioKind, MediaKind, MediaSource
from app.models.media import AudioAsset, MediaAsset
from app.models.project import Project
from app.models.scene import Scene
from app.providers import get_registry
from app.providers.base import StockMediaItem
from app.schemas.common import Message, Page
from app.schemas.media import (
    AudioAssetPublic,
    MediaAssetPublic,
    MediaUpdate,
    StockImportRequest,
    StockSearchResult,
    StorageUsage,
    UploadCompleteRequest,
    UploadInitRequest,
    UploadInitResponse,
)
from app.services.billing_service import ensure_subscription
from app.services.media_service import (
    delete_media_asset,
    ext_for,
    kind_for_content_type,
    save_audio_asset_sync,
    save_media_asset_sync,
    storage_breakdown,
    url_for,
)
from app.storage.base import build_key
from app.storage.factory import get_storage
from app.storage.local import LocalStorage, verify_local_signature

router = APIRouter()

ALLOWED_UPLOAD_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/quicktime", "video/webm", "video/x-matroska",
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg", "audio/aac", "audio/mp4", "audio/flac",
}


def _media_public(a: MediaAsset) -> MediaAssetPublic:
    p = MediaAssetPublic.model_validate(a)
    p.url = url_for(a.storage_key, filename=a.filename)
    p.thumbnail_url = url_for(a.thumbnail_key or (a.storage_key if a.kind == MediaKind.IMAGE else None))
    return p


def _audio_public(a: AudioAsset) -> AudioAssetPublic:
    p = AudioAssetPublic.model_validate(a)
    p.url = url_for(a.storage_key, filename=a.filename)
    return p


async def _check_project(db: DB, user, project_id: uuid.UUID | None) -> None:
    if project_id is None:
        return
    proj = await db.get(Project, project_id)
    if proj is None or (proj.owner_id != user.id and not user.is_superuser):
        raise NotFoundError("Project not found")


async def _check_quota(db: DB, user, incoming_bytes: int) -> None:
    sub = await ensure_subscription(db, user)
    if user.storage_bytes_used + incoming_bytes > sub.storage_limit_bytes:
        raise ValidationError("Storage quota exceeded. Delete unused media or upgrade your plan.", details={"used": user.storage_bytes_used, "limit": sub.storage_limit_bytes})


# --- signed local file serving (dev / single-node deployments) ---------------------------


@router.api_route("/files/{key:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_local_file(key: str, request: Request, expires: int = Query(...), signature: str = Query(...), download: str | None = None) -> Response:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise NotFoundError("Local file serving is disabled for this storage backend")
    if not verify_local_signature(key, expires, signature, "GET"):
        raise PermissionDeniedError("Invalid or expired media signature")
    try:
        path: Path = storage.local_path(key)
    except ValueError as exc:
        raise NotFoundError("File not found") from exc
    if not path.exists():
        raise NotFoundError("File not found")
    headers = {"Cache-Control": "private, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{download}"'
    return FileResponse(path, media_type=storage.content_type(key), headers=headers)


@router.put("/files/{key:path}", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
async def receive_local_upload(key: str, request: Request, expires: int = Query(...), signature: str = Query(...)) -> Response:
    """Target of `signed_put_url` when using the local backend (mirrors S3 presigned PUT)."""
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise NotFoundError("Local uploads are disabled for this storage backend")
    if not verify_local_signature(key, expires, signature, "PUT"):
        raise PermissionDeniedError("Invalid or expired upload signature")
    body = await request.body()
    ctype = request.headers.get("content-type", "application/octet-stream")
    await anyio.to_thread.run_sync(storage.put_bytes, key, body, ctype)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- uploads ------------------------------------------------------------------------------


@router.post("/uploads/init", response_model=UploadInitResponse, summary="Get a presigned URL to upload a file directly to object storage")
async def upload_init(body: UploadInitRequest, user: CurrentUser, db: DB) -> UploadInitResponse:
    if body.content_type not in ALLOWED_UPLOAD_TYPES:
        raise ValidationError(f"Unsupported content type {body.content_type}")
    await _check_project(db, user, body.project_id)
    await _check_quota(db, user, body.size_bytes)
    kind = body.kind or kind_for_content_type(body.content_type)
    safe_name = f"{uuid.uuid4().hex[:8]}-{Path(body.filename).stem[:80]}.{ext_for(body.content_type, Path(body.filename).suffix.lstrip('.') or 'bin')}"
    key = build_key(user.id, "uploads/" + kind.value + "s", safe_name, body.project_id)
    url = get_storage().signed_put_url(key, body.content_type, 900)
    return UploadInitResponse(upload_url=url, storage_key=key, method="PUT", headers={"Content-Type": body.content_type}, expires_in=900)


@router.post("/uploads/complete", response_model=MediaAssetPublic | AudioAssetPublic, status_code=status.HTTP_201_CREATED, summary="Register an uploaded object as a media/audio asset")
async def upload_complete(body: UploadCompleteRequest, user: CurrentUser, db: DB) -> MediaAssetPublic | AudioAssetPublic:
    if not body.storage_key.startswith(f"users/{user.id}/"):
        raise PermissionDeniedError("Storage key does not belong to you")
    storage = get_storage()
    if not await anyio.to_thread.run_sync(storage.exists, body.storage_key):
        raise ValidationError("Upload not found in storage - did the PUT succeed?")
    await _check_project(db, user, body.project_id)
    data = await anyio.to_thread.run_sync(storage.get_bytes, body.storage_key)
    # Re-store under the canonical layout with probing/thumbnailing, then drop the temp object.
    kind = body.kind or kind_for_content_type(body.content_type)
    if kind == MediaKind.AUDIO:
        asset = await db.run_sync(lambda s: save_audio_asset_sync(s, owner_id=user.id, data=data, content_type=body.content_type, filename=body.filename, kind=body.audio_kind or AudioKind.MUSIC, source=MediaSource.UPLOAD, project_id=body.project_id, tags=body.tags))
        await anyio.to_thread.run_sync(storage.delete, body.storage_key)
        return _audio_public(asset)
    asset = await db.run_sync(lambda s: save_media_asset_sync(s, owner_id=user.id, data=data, content_type=body.content_type, filename=body.filename, source=MediaSource.UPLOAD, project_id=body.project_id, tags=body.tags, is_reusable=body.is_reusable, category="uploads"))
    await anyio.to_thread.run_sync(storage.delete, body.storage_key)
    return _media_public(asset)


@router.post("/upload", response_model=MediaAssetPublic | AudioAssetPublic, status_code=status.HTTP_201_CREATED, summary="Simple multipart upload (small files; proxied through the API)")
@limiter.limit("30/minute")
async def upload_direct(request: Request, user: CurrentUser, db: DB, file: UploadFile = File(...), project_id: uuid.UUID | None = Form(default=None), audio_kind: AudioKind | None = Form(default=None), tags: str = Form(default="")) -> MediaAssetPublic | AudioAssetPublic:
    ctype = file.content_type or "application/octet-stream"
    if ctype not in ALLOWED_UPLOAD_TYPES:
        raise ValidationError(f"Unsupported content type {ctype}")
    data = await file.read()
    if len(data) > settings.max_direct_upload_bytes:
        raise ValidationError(f"File too large for direct upload (max {settings.max_direct_upload_bytes // (1024 * 1024)} MB). Use /media/uploads/init.")
    await _check_project(db, user, project_id)
    await _check_quota(db, user, len(data))
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    kind = kind_for_content_type(ctype)
    fname = file.filename or f"upload.{ext_for(ctype)}"
    if kind == MediaKind.AUDIO:
        asset = await db.run_sync(lambda s: save_audio_asset_sync(s, owner_id=user.id, data=data, content_type=ctype, filename=fname, kind=audio_kind or AudioKind.MUSIC, source=MediaSource.UPLOAD, project_id=project_id, tags=tag_list))
        return _audio_public(asset)
    asset = await db.run_sync(lambda s: save_media_asset_sync(s, owner_id=user.id, data=data, content_type=ctype, filename=fname, source=MediaSource.UPLOAD, project_id=project_id, tags=tag_list, is_reusable=True, category="uploads"))
    return _media_public(asset)


# --- assets -------------------------------------------------------------------------------


@router.get("", response_model=Page[MediaAssetPublic])
async def list_media(user: CurrentUser, db: DB, project_id: uuid.UUID | None = None, kind: MediaKind | None = None, source: MediaSource | None = None, q: str | None = None, reusable_only: bool = False, page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=100)) -> Page[MediaAssetPublic]:
    stmt = select(MediaAsset).where(MediaAsset.owner_id == user.id)
    if project_id:
        stmt = stmt.where(or_(MediaAsset.project_id == project_id, MediaAsset.is_reusable.is_(True)))
    if kind:
        stmt = stmt.where(MediaAsset.kind == kind)
    if source:
        stmt = stmt.where(MediaAsset.source == source)
    if reusable_only:
        stmt = stmt.where(MediaAsset.is_reusable.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(MediaAsset.filename.ilike(like), MediaAsset.prompt.ilike(like)))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(MediaAsset.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[_media_public(a) for a in rows], total=total, page=page, page_size=page_size)


@router.get("/storage", response_model=StorageUsage)
async def storage_usage(user: CurrentUser, db: DB) -> StorageUsage:
    sub = await ensure_subscription(db, user)
    br = await storage_breakdown(db, user.id)
    return StorageUsage(used_bytes=max(br["used_bytes"], user.storage_bytes_used), limit_bytes=sub.storage_limit_bytes, by_kind=br["by_kind"], asset_count=br["asset_count"])


@router.get("/audio", response_model=list[AudioAssetPublic], summary="Music / SFX library (system tracks + your uploads)")
async def list_audio(user: CurrentUser, db: DB, kind: AudioKind | None = None, mood: str | None = None, project_id: uuid.UUID | None = None) -> list[AudioAssetPublic]:
    stmt = select(AudioAsset).where(or_(AudioAsset.owner_id == user.id, AudioAsset.is_system.is_(True)))
    if kind:
        stmt = stmt.where(AudioAsset.kind == kind)
    if mood:
        stmt = stmt.where(AudioAsset.mood == mood)
    if project_id:
        stmt = stmt.where(or_(AudioAsset.project_id == project_id, AudioAsset.project_id.is_(None), AudioAsset.is_system.is_(True)))
    rows = (await db.execute(stmt.order_by(AudioAsset.is_system.desc(), AudioAsset.created_at.desc()))).scalars().all()
    return [_audio_public(a) for a in rows]


@router.delete("/audio/{asset_id}", response_model=Message)
async def delete_audio(asset_id: uuid.UUID, user: CurrentUser, db: DB) -> Message:
    a = await db.get(AudioAsset, asset_id)
    if a is None or a.owner_id != user.id:
        raise NotFoundError("Audio asset not found")
    if a.is_system:
        raise PermissionDeniedError("System tracks cannot be deleted")
    await anyio.to_thread.run_sync(get_storage().delete, a.storage_key)
    await db.delete(a)
    return Message(message="Audio deleted")


@router.get("/{asset_id}", response_model=MediaAssetPublic)
async def get_media(asset_id: uuid.UUID, user: CurrentUser, db: DB) -> MediaAssetPublic:
    a = await db.get(MediaAsset, asset_id)
    if a is None or (a.owner_id != user.id and not user.is_superuser):
        raise NotFoundError("Asset not found")
    return _media_public(a)


@router.patch("/{asset_id}", response_model=MediaAssetPublic)
async def update_media(asset_id: uuid.UUID, body: MediaUpdate, user: CurrentUser, db: DB) -> MediaAssetPublic:
    a = await db.get(MediaAsset, asset_id)
    if a is None or a.owner_id != user.id:
        raise NotFoundError("Asset not found")
    data = body.model_dump(exclude_unset=True)
    if "project_id" in data:
        await _check_project(db, user, data["project_id"])
    for k, v in data.items():
        setattr(a, k, v)
    return _media_public(a)


@router.delete("/{asset_id}", response_model=Message)
async def delete_media(asset_id: uuid.UUID, user: CurrentUser, db: DB) -> Message:
    a = await db.get(MediaAsset, asset_id)
    if a is None or a.owner_id != user.id:
        raise NotFoundError("Asset not found")
    in_use = (await db.execute(select(func.count()).select_from(Scene).where(Scene.visual_asset_id == a.id))).scalar_one()
    if in_use:
        raise ValidationError(f"Asset is used by {in_use} scene(s). Replace it first.")
    await delete_media_asset(db, a)
    return Message(message="Asset deleted")


# --- stock media --------------------------------------------------------------------------


@router.get("/stock/search", response_model=list[StockSearchResult], summary="Search stock footage/photos through the configured provider")
@limiter.limit("60/minute")
async def stock_search(request: Request, user: CurrentUser, q: str = Query(min_length=2, max_length=120), kind: str = Query("video", pattern="^(image|video)$"), orientation: str = Query("landscape"), per_page: int = Query(12, ge=1, le=40), page: int = Query(1, ge=1), provider: str | None = None, min_duration: float | None = None) -> list[StockSearchResult]:
    p = get_registry().stock(provider)
    items = await anyio.to_thread.run_sync(lambda: p.search(q, kind=kind, orientation=orientation, per_page=per_page, page=page, min_duration=min_duration))
    return [StockSearchResult(**i.__dict__) for i in items]


@router.post("/stock/import", response_model=MediaAssetPublic, status_code=status.HTTP_201_CREATED, summary="Download a stock item into your media library")
@limiter.limit("30/minute")
async def stock_import(request: Request, body: StockImportRequest, user: CurrentUser, db: DB) -> MediaAssetPublic:
    await _check_project(db, user, body.project_id)
    item = StockMediaItem(**body.item.model_dump())
    provider = get_registry().stock(item.source if item.source != "mock" else None)
    data, ctype = await anyio.to_thread.run_sync(provider.download, item)
    await _check_quota(db, user, len(data))
    asset = await db.run_sync(
        lambda s: save_media_asset_sync(s, owner_id=user.id, project_id=body.project_id, scene_id=body.scene_id, data=data, content_type=ctype, filename=f"stock-{item.source}-{item.id}.{ext_for(ctype)}", source=MediaSource.STOCK, provider=item.source, provider_ref=item.id, width=item.width, height=item.height, duration_seconds=item.duration_seconds, tags=["stock", item.kind], is_reusable=True, category="stock")
    )
    if body.scene_id:
        scene = await db.get(Scene, body.scene_id)
        if scene and scene.project_id == body.project_id:
            scene.visual_asset_id = asset.id
    return _media_public(asset)
