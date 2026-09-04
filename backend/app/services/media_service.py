"""Persisting generated/uploaded binaries as MediaAsset / AudioAsset rows + storage objects."""

from __future__ import annotations

import hashlib
import mimetypes
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import AudioKind, MediaKind, MediaSource
from app.models.media import AudioAsset, MediaAsset, Voiceover
from app.models.user import User
from app.storage import get_storage
from app.storage.base import build_key
from app.utils.ffmpeg import media_duration, run_ffmpeg, video_dimensions

log = get_logger(__name__)

EXT_BY_TYPE = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/aac": "aac",
    "audio/mp4": "m4a",
    "text/vtt": "vtt",
    "application/x-subrip": "srt",
}


def kind_for_content_type(content_type: str) -> MediaKind:
    if content_type.startswith("image/"):
        return MediaKind.IMAGE
    if content_type.startswith("video/"):
        return MediaKind.VIDEO
    if content_type.startswith("audio/"):
        return MediaKind.AUDIO
    if content_type.startswith("font/") or "font" in content_type:
        return MediaKind.FONT
    if content_type in ("text/vtt", "application/x-subrip"):
        return MediaKind.SUBTITLE
    return MediaKind.OTHER


def ext_for(content_type: str, fallback: str = "bin") -> str:
    return EXT_BY_TYPE.get(content_type) or (mimetypes.guess_extension(content_type) or f".{fallback}").lstrip(".")


def url_for(key: str | None, *, filename: str | None = None, expires: int | None = None) -> str | None:
    if not key:
        return None
    try:
        return get_storage().signed_get_url(key, expires, filename=filename)
    except Exception as exc:  # pragma: no cover
        log.warning("signed url failed", key=key, error=str(exc))
        return None


def make_thumbnail(data: bytes, content_type: str, *, size: int = 480) -> bytes | None:
    """Generate a JPEG thumbnail for images and videos (first frame)."""
    try:
        if content_type.startswith("image/"):
            from PIL import Image
            import io

            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((size, size))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            return buf.getvalue()
        if content_type.startswith("video/"):
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / f"src.{ext_for(content_type, 'mp4')}"
                src.write_bytes(data)
                out = Path(tmp) / "thumb.jpg"
                run_ffmpeg(["-ss", "0.5", "-i", str(src), "-frames:v", "1", "-vf", f"scale={size}:-2", "-q:v", "4", str(out)], timeout=60)
                return out.read_bytes()
    except Exception as exc:
        log.warning("thumbnail failed", error=str(exc))
    return None


def probe_media(data: bytes, content_type: str) -> dict:
    """Return width/height/duration/fps for stored bytes."""
    info: dict = {}
    try:
        if content_type.startswith("image/"):
            from PIL import Image
            import io

            im = Image.open(io.BytesIO(data))
            info["width"], info["height"] = im.size
        elif content_type.startswith(("video/", "audio/")):
            with tempfile.NamedTemporaryFile(suffix=f".{ext_for(content_type)}", delete=True) as f:
                f.write(data)
                f.flush()
                info["duration_seconds"] = media_duration(f.name)
                if content_type.startswith("video/"):
                    w, h, fps = video_dimensions(f.name)
                    info.update(width=w or None, height=h or None, fps=fps or None)
    except Exception as exc:
        log.warning("probe failed", error=str(exc))
    return info


# --------------------------------------------------------------------------- sync (workers)


def save_media_asset_sync(
    db: Session,
    *,
    owner_id: uuid.UUID,
    data: bytes,
    content_type: str,
    filename: str,
    source: MediaSource,
    project_id: uuid.UUID | None = None,
    scene_id: uuid.UUID | None = None,
    prompt: str | None = None,
    provider: str | None = None,
    provider_ref: str | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_seconds: float | None = None,
    fps: float | None = None,
    tags: list[str] | None = None,
    is_reusable: bool = False,
    category: str | None = None,
    make_thumb: bool = True,
) -> MediaAsset:
    storage = get_storage()
    kind = kind_for_content_type(content_type)
    key = build_key(owner_id, category or kind.value + "s", filename, project_id)
    storage.put_bytes(key, data, content_type)
    thumb_key = None
    if make_thumb and kind in (MediaKind.IMAGE, MediaKind.VIDEO):
        thumb = make_thumbnail(data, content_type)
        if thumb:
            thumb_key = key.rsplit(".", 1)[0] + ".thumb.jpg"
            storage.put_bytes(thumb_key, thumb, "image/jpeg")
    if width is None or (kind == MediaKind.VIDEO and duration_seconds is None):
        info = probe_media(data, content_type)
        width = width or info.get("width")
        height = height or info.get("height")
        duration_seconds = duration_seconds or info.get("duration_seconds")
        fps = fps or info.get("fps")
    asset = MediaAsset(
        owner_id=owner_id,
        project_id=project_id,
        scene_id=scene_id,
        kind=kind,
        source=source,
        storage_key=key,
        thumbnail_key=thumb_key,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        fps=fps,
        checksum=hashlib.sha256(data).hexdigest(),
        prompt=prompt,
        provider=provider,
        provider_ref=provider_ref,
        tags=tags or [],
        is_reusable=is_reusable,
        is_uploaded=True,
    )
    db.add(asset)
    db.execute(update(User).where(User.id == owner_id).values(storage_bytes_used=User.storage_bytes_used + len(data)))
    db.flush()
    return asset


def save_voiceover_audio_sync(db: Session, voiceover: Voiceover, data: bytes, content_type: str, *, owner_id: uuid.UUID) -> Voiceover:
    storage = get_storage()
    ext = ext_for(content_type, "mp3")
    key = build_key(owner_id, "voiceovers", f"scene-{voiceover.scene_id or 'x'}-v{uuid.uuid4().hex[:6]}.{ext}", voiceover.project_id)
    storage.put_bytes(key, data, content_type)
    voiceover.storage_key = key
    voiceover.content_type = content_type
    voiceover.size_bytes = len(data)
    db.execute(update(User).where(User.id == owner_id).values(storage_bytes_used=User.storage_bytes_used + len(data)))
    db.flush()
    return voiceover


def save_audio_asset_sync(
    db: Session,
    *,
    owner_id: uuid.UUID,
    data: bytes,
    content_type: str,
    filename: str,
    kind: AudioKind,
    source: MediaSource = MediaSource.SYSTEM,
    project_id: uuid.UUID | None = None,
    mood: str | None = None,
    tags: list[str] | None = None,
    is_system: bool = False,
    license: str | None = None,
) -> AudioAsset:
    storage = get_storage()
    key = build_key(owner_id, "audio", filename, project_id)
    storage.put_bytes(key, data, content_type)
    info = probe_media(data, content_type)
    asset = AudioAsset(
        owner_id=owner_id,
        project_id=project_id,
        kind=kind,
        source=source,
        storage_key=key,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        duration_seconds=info.get("duration_seconds"),
        mood=mood,
        tags=tags or [],
        is_system=is_system,
        license=license,
    )
    db.add(asset)
    db.execute(update(User).where(User.id == owner_id).values(storage_bytes_used=User.storage_bytes_used + len(data)))
    db.flush()
    return asset


# --------------------------------------------------------------------------- async (API)


async def delete_media_asset(db: AsyncSession, asset: MediaAsset) -> None:
    storage = get_storage()
    for key in (asset.storage_key, asset.thumbnail_key):
        if key:
            try:
                storage.delete(key)
            except Exception as exc:  # pragma: no cover
                log.warning("storage delete failed", key=key, error=str(exc))
    await db.execute(
        update(User).where(User.id == asset.owner_id).values(storage_bytes_used=func.greatest(User.storage_bytes_used - asset.size_bytes, 0))
    )
    await db.delete(asset)


async def storage_breakdown(db: AsyncSession, user_id: uuid.UUID) -> dict:
    rows = (
        await db.execute(
            select(MediaAsset.kind, func.coalesce(func.sum(MediaAsset.size_bytes), 0), func.count())
            .where(MediaAsset.owner_id == user_id)
            .group_by(MediaAsset.kind)
        )
    ).all()
    by_kind = {str(k.value): int(b) for k, b, _ in rows}
    count = sum(int(c) for *_, c in rows)
    audio_bytes = (await db.execute(select(func.coalesce(func.sum(AudioAsset.size_bytes), 0)).where(AudioAsset.owner_id == user_id))).scalar_one()
    vo_bytes = (await db.execute(select(func.coalesce(func.sum(Voiceover.size_bytes), 0)).join(Voiceover.project).where(Voiceover.project.has(owner_id=user_id)))).scalar_one()
    by_kind["audio"] = by_kind.get("audio", 0) + int(audio_bytes)
    by_kind["voiceover"] = int(vo_bytes)
    return {"by_kind": by_kind, "asset_count": count, "used_bytes": sum(by_kind.values())}


def default_local_path(key: str) -> Path | None:
    """When using local storage, expose the direct path to avoid copies inside workers."""
    if settings.storage_backend == "local":
        from app.storage.local import LocalStorage

        st = get_storage()
        if isinstance(st, LocalStorage):
            return st.local_path(key)
    return None
