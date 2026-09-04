"""Per-scene voiceover generation with caching by (text, voice, provider, speed)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import UsageKind
from app.models.media import Voiceover
from app.models.project import Project
from app.models.scene import Scene
from app.models.user import User
from app.providers import get_registry
from app.services.billing_service import record_usage_sync
from app.services.media_service import save_voiceover_audio_sync
from app.utils.text import sha256_text

log = get_logger(__name__)
MAX_PARALLEL_TTS = 3


def voice_config(project: Project, **overrides) -> dict:
    cfg = dict((project.settings or {}).get("voice") or {})
    cfg.setdefault("voice_id", "mock-aria")
    cfg.setdefault("language", project.language or "en")
    cfg.setdefault("speed", 1.0)
    cfg.setdefault("style", "narration")
    cfg.setdefault("provider", None)
    for k, v in overrides.items():
        if v is not None:
            cfg[k] = v
    return cfg


def generate_voiceovers_sync(
    db: Session,
    project: Project,
    user: User,
    scenes: list[Scene],
    *,
    force: bool = False,
    voice_id: str | None = None,
    provider: str | None = None,
    language: str | None = None,
    style: str | None = None,
    speed: float | None = None,
    job_id=None,
    progress: Callable[[float, str], None] | None = None,
) -> list[Voiceover]:
    cfg = voice_config(project, voice_id=voice_id, provider=provider, language=language, style=style, speed=speed)
    tts = get_registry().tts(cfg.get("provider"))
    provider_name = tts.name
    todo: list[Scene] = []
    reused: list[Voiceover] = []

    for scene in scenes:
        if not scene.narration.strip():
            continue
        text_hash = sha256_text(scene.narration.strip())
        if not force and scene.voiceover_id:
            existing = db.get(Voiceover, scene.voiceover_id)
            if (
                existing
                and existing.status == "ready"
                and existing.text_hash == text_hash
                and existing.voice_id == cfg["voice_id"]
                and existing.provider == provider_name
                and abs(existing.speed - float(cfg["speed"])) < 1e-6
            ):
                reused.append(existing)
                continue
        # Cache hit from another scene/project version with identical text+voice
        cached = db.execute(
            select(Voiceover).where(
                Voiceover.project_id == project.id,
                Voiceover.text_hash == text_hash,
                Voiceover.voice_id == cfg["voice_id"],
                Voiceover.provider == provider_name,
                Voiceover.speed == float(cfg["speed"]),
                Voiceover.status == "ready",
            )
        ).scalars().first()
        if cached and not force:
            _attach(db, scene, cached)
            reused.append(cached)
            continue
        todo.append(scene)

    total = len(todo) or 1
    done_count = 0
    results: list[Voiceover] = list(reused)

    def synth(scene: Scene) -> tuple[Scene, object, Exception | None]:
        try:
            res = tts.synthesize(
                scene.narration.strip(),
                voice_id=cfg["voice_id"],
                language=cfg["language"],
                speed=float(cfg["speed"]),
                style=cfg.get("style"),
                output_format="mp3",
            )
            return scene, res, None
        except Exception as exc:  # captured per scene; the job decides whether to fail
            return scene, None, exc

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_TTS) as pool:
        for scene, res, err in pool.map(synth, todo):
            done_count += 1
            if err is not None or res is None:
                failures.append(f"scene {scene.order_index + 1}: {err}")
                log.warning("tts failed", scene_id=str(scene.id), error=str(err))
                continue
            db.execute(update(Voiceover).where(Voiceover.scene_id == scene.id).values(is_current=False))
            vo = Voiceover(
                project_id=project.id,
                scene_id=scene.id,
                text=scene.narration.strip(),
                text_hash=sha256_text(scene.narration.strip()),
                provider=provider_name,
                voice_id=cfg["voice_id"],
                voice_name=cfg.get("voice_name"),
                language=cfg["language"],
                style=cfg.get("style"),
                speed=float(cfg["speed"]),
                duration_seconds=res.duration_seconds,
                word_timings=[asdict(w) for w in res.word_timings],
                status="ready",
                is_current=True,
            )
            db.add(vo)
            db.flush()
            save_voiceover_audio_sync(db, vo, res.data, res.content_type, owner_id=user.id)
            _attach(db, scene, vo)
            record_usage_sync(
                db, user, UsageKind.TTS_CHARACTERS, len(scene.narration), "chars",
                metrics=res.usage, project_id=project.id, job_id=job_id,
            )
            results.append(vo)
            if progress:
                progress(done_count / total, f"Generating voiceover... {done_count}/{total} scenes")
            db.commit()

    if failures and len(failures) == len(todo) and todo:
        raise RuntimeError("Voiceover generation failed for every scene: " + "; ".join(failures[:3]))
    return results


def _attach(db: Session, scene: Scene, vo: Voiceover) -> None:
    scene.voiceover_id = vo.id
    # Scene duration follows the real narration length (+ small tail for breathing room)
    if vo.duration_seconds:
        scene.duration_seconds = round(float(vo.duration_seconds) + 0.35, 3)
    scene.status = "voiced" if scene.visual_asset_id is None else "ready"
    db.flush()


def voiceovers_for_scenes(db: Session, scenes: list[Scene]) -> dict[uuid.UUID, Voiceover]:
    ids = [s.voiceover_id for s in scenes if s.voiceover_id]
    if not ids:
        return {}
    rows = db.execute(select(Voiceover).where(Voiceover.id.in_(ids))).scalars().all()
    by_id = {v.id: v for v in rows}
    return {s.id: by_id[s.voiceover_id] for s in scenes if s.voiceover_id in by_id}
