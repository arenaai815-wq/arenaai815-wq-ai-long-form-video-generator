"""Timeline document construction and server-side edit operations.

The timeline is the single source of truth for rendering. It is (re)built from scenes
after generation stages and then edited freely in the browser. `sync_from_scenes`
preserves user edits on tracks that are not scene-derived (music, sfx, text overlays).
"""

from __future__ import annotations

import copy

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.enums import dimensions_for
from app.models.media import AudioAsset, MediaAsset, Voiceover
from app.models.project import Project
from app.models.scene import Scene
from app.models.timeline import Timeline
from app.schemas.timeline import TimelineDocument

SCENE_TRACK_ID = "track-visuals"
VOICE_TRACK_ID = "track-voiceover"
MUSIC_TRACK_ID = "track-music"
SFX_TRACK_ID = "track-sfx"
TEXT_TRACK_ID = "track-text"
CAPTIONS_TRACK_ID = "track-captions"


def _checksum(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:32]


def empty_document(project: Project) -> dict[str, Any]:
    w, h = dimensions_for(project.aspect_ratio, project.resolution)
    settings_ = project.settings or {}
    cap = {**(settings_.get("captions") or {})}
    wm = settings_.get("watermark") or {}
    doc = TimelineDocument(
        width=w,
        height=h,
        tracks=[
            {"id": TEXT_TRACK_ID, "kind": "text", "name": "Text overlays", "clips": []},
            {"id": SCENE_TRACK_ID, "kind": "video", "name": "Scenes", "clips": []},
            {"id": VOICE_TRACK_ID, "kind": "voiceover", "name": "Voiceover", "clips": []},
            {"id": MUSIC_TRACK_ID, "kind": "music", "name": "Music", "clips": [], "volume": float((settings_.get("music") or {}).get("volume", 0.12))},
            {"id": SFX_TRACK_ID, "kind": "sfx", "name": "Sound effects", "clips": []},
            {"id": CAPTIONS_TRACK_ID, "kind": "captions", "name": "Captions", "clips": []},
        ],
        captions={k: v for k, v in cap.items() if k in TimelineDocument.model_fields["captions"].annotation.model_fields} if cap else {},
        watermark={"enabled": bool(wm.get("enabled")), "asset_id": str(wm["asset_id"]) if wm.get("asset_id") else None, "text": wm.get("text"), "position": wm.get("position", "bottom_right"), "opacity": float(wm.get("opacity", 0.6))},
    )
    return doc.model_dump()


def get_or_create_timeline(db: Session, project: Project) -> Timeline:
    tl = db.execute(select(Timeline).where(Timeline.project_id == project.id)).scalar_one_or_none()
    if tl is None:
        w, h = dimensions_for(project.aspect_ratio, project.resolution)
        tl = Timeline(project_id=project.id, width=w, height=h, data=empty_document(project))
        db.add(tl)
        db.flush()
    return tl


def sync_from_scenes(db: Session, project: Project, scenes: list[Scene], *, preserve_user_edits: bool = True) -> Timeline:
    """Rebuild scene-derived tracks (visuals, voiceover, text) from the scene list."""
    tl = get_or_create_timeline(db, project)
    # Deep copy: JSON columns are compared by value on flush, so mutating the loaded
    # dict in place would make SQLAlchemy think nothing changed.
    doc = copy.deepcopy(tl.data) if tl.data else empty_document(project)
    tracks = {t["id"]: t for t in doc.get("tracks", [])}
    for base in empty_document(project)["tracks"]:
        tracks.setdefault(base["id"], base)

    settings_ = project.settings or {}
    intro = settings_.get("intro") or {}
    outro = settings_.get("outro") or {}
    intro_d = float(intro.get("duration") or 0) if intro.get("enabled", True) else 0.0
    outro_d = float(outro.get("duration") or 0) if outro.get("enabled", True) else 0.0

    vo_ids = [s.voiceover_id for s in scenes if s.voiceover_id]
    voiceovers = {v.id: v for v in db.execute(select(Voiceover).where(Voiceover.id.in_(vo_ids))).scalars()} if vo_ids else {}
    asset_ids = [s.visual_asset_id for s in scenes if s.visual_asset_id]
    assets = {a.id: a for a in db.execute(select(MediaAsset).where(MediaAsset.id.in_(asset_ids))).scalars()} if asset_ids else {}

    # Keep previous per-clip user tweaks (volume/fades/effects) keyed by scene id
    prev_visual = {c.get("scene_id"): c for c in tracks[SCENE_TRACK_ID].get("clips", []) if c.get("scene_id")} if preserve_user_edits else {}
    prev_voice = {c.get("scene_id"): c for c in tracks[VOICE_TRACK_ID].get("clips", []) if c.get("scene_id")} if preserve_user_edits else {}

    visual_clips, voice_clips, text_clips = [], [], []
    t = 0.0
    if intro_d > 0:
        text_clips.append(
            {
                "id": "clip-intro-title",
                "scene_id": None,
                "asset_id": None,
                "asset_kind": "text",
                "start": 0.0,
                "duration": intro_d,
                "label": "Intro title",
                "text": {"content": intro.get("title") or project.title, "font_size": 84, "position": "center", "animation": "fade", "color": "#FFFFFF"},
            }
        )
        visual_clips.append({"id": "clip-intro-bg", "scene_id": None, "asset_id": None, "asset_kind": "text", "start": 0.0, "duration": intro_d, "label": "Intro", "transition_in": {"type": "fade", "duration": 0.5}, "effect": {"type": "none", "intensity": 0}})
        t = intro_d

    for scene in sorted(scenes, key=lambda s: s.order_index):
        vo = voiceovers.get(scene.voiceover_id) if scene.voiceover_id else None
        asset = assets.get(scene.visual_asset_id) if scene.visual_asset_id else None
        dur = float(scene.duration_seconds or 5.0)
        old = prev_visual.get(str(scene.id), {})
        clip = {
            "id": old.get("id") or f"clip-v-{scene.id}",
            "scene_id": str(scene.id),
            "asset_id": str(asset.id) if asset else None,
            "asset_kind": asset.kind.value if asset else "text",
            "start": round(t, 3),
            "duration": round(dur, 3),
            "trim_start": float(old.get("trim_start", 0)),
            "trim_end": 0,
            "label": scene.title or f"Scene {scene.order_index + 1}",
            "transition_in": {"type": scene.transition or "fade", "duration": float(scene.transition_duration or 0.5)},
            "effect": old.get("effect") or {"type": scene.motion_effect or "ken_burns", "intensity": 0.12},
        }
        visual_clips.append(clip)
        if vo and vo.storage_key:
            oldv = prev_voice.get(str(scene.id), {})
            voice_clips.append(
                {
                    "id": oldv.get("id") or f"clip-a-{scene.id}",
                    "scene_id": str(scene.id),
                    "asset_id": str(vo.id),
                    "asset_kind": "voiceover",
                    "start": round(t, 3),
                    "duration": round(float(vo.duration_seconds or dur), 3),
                    "volume": float(oldv.get("volume", 1.0)),
                    "fade_in": float(oldv.get("fade_in", 0.02)),
                    "fade_out": float(oldv.get("fade_out", 0.05)),
                    "label": f"VO {scene.order_index + 1}",
                }
            )
        if scene.on_screen_text:
            text_clips.append(
                {
                    "id": f"clip-t-{scene.id}",
                    "scene_id": str(scene.id),
                    "asset_id": None,
                    "asset_kind": "text",
                    "start": round(t + 0.4, 3),
                    "duration": round(min(dur - 0.6, 5.0), 3) if dur > 1.5 else round(dur, 3),
                    "label": "On-screen text",
                    "text": {"content": scene.on_screen_text, "font_size": 48, "position": "bottom_left" if (doc.get("captions") or {}).get("position", "bottom") != "bottom" else "top_left", "animation": "slide_up", "background": "#000000"},
                }
            )
        t += dur

    if outro_d > 0:
        visual_clips.append({"id": "clip-outro-bg", "scene_id": None, "asset_id": None, "asset_kind": "text", "start": round(t, 3), "duration": outro_d, "label": "Outro", "transition_in": {"type": "fadeblack", "duration": 0.6}, "effect": {"type": "none", "intensity": 0}})
        text_clips.append({"id": "clip-outro-text", "scene_id": None, "asset_id": None, "asset_kind": "text", "start": round(t, 3), "duration": outro_d, "label": "Outro text", "text": {"content": f"{outro.get('text') or 'Thanks for watching'}\n{outro.get('cta') or ''}".strip(), "font_size": 64, "position": "center", "animation": "fade"}})
        t += outro_d

    # Keep user-authored text clips (not scene/intro/outro derived)
    user_text = [c for c in tracks[TEXT_TRACK_ID].get("clips", []) if not str(c.get("id", "")).startswith(("clip-t-", "clip-intro", "clip-outro"))] if preserve_user_edits else []
    tracks[SCENE_TRACK_ID]["clips"] = visual_clips
    tracks[VOICE_TRACK_ID]["clips"] = voice_clips
    tracks[TEXT_TRACK_ID]["clips"] = user_text + text_clips

    # Music: fill the whole duration with the configured bed (or default system track)
    music_cfg = settings_.get("music") or {}
    music_track = tracks[MUSIC_TRACK_ID]
    if music_cfg.get("enabled", True) and not music_track.get("clips"):
        asset_id = music_cfg.get("asset_id")
        if not asset_id:
            sys_music = db.execute(select(AudioAsset).where(AudioAsset.is_system.is_(True), AudioAsset.kind == "music").order_by(AudioAsset.created_at)).scalars().first()
            asset_id = str(sys_music.id) if sys_music else None
        if asset_id:
            music_track["clips"] = [
                {"id": "clip-music-bed", "scene_id": None, "asset_id": str(asset_id), "asset_kind": "audio", "start": 0.0, "duration": round(t, 3), "volume": float(music_cfg.get("volume", 0.12)), "fade_in": float(music_cfg.get("fade_in", 1.5)), "fade_out": float(music_cfg.get("fade_out", 3.0)), "label": "Music bed", "trim_start": 0}
            ]
    elif music_track.get("clips"):
        for c in music_track["clips"]:
            if c.get("id") == "clip-music-bed":
                c["duration"] = round(t, 3)

    order = [TEXT_TRACK_ID, SCENE_TRACK_ID, VOICE_TRACK_ID, MUSIC_TRACK_ID, SFX_TRACK_ID, CAPTIONS_TRACK_ID]
    doc["tracks"] = [tracks[i] for i in order if i in tracks] + [tr for tid, tr in tracks.items() if tid not in order]
    doc["duration"] = round(t, 3)
    w, h = dimensions_for(project.aspect_ratio, project.resolution)
    doc["width"], doc["height"] = w, h
    tl.data = doc
    flag_modified(tl, "data")
    tl.width, tl.height = w, h
    tl.duration_seconds = round(t, 3)
    tl.version += 1
    tl.checksum = _checksum(doc)
    project.estimated_duration_seconds = round(t, 3)
    db.flush()
    return tl


def save_document(db: Session, tl: Timeline, doc: TimelineDocument) -> Timeline:
    data = doc.model_dump()
    data["duration"] = doc.compute_duration()
    snaps = list(tl.snapshots or [])
    snaps.append({"version": tl.version, "checksum": tl.checksum, "duration": tl.duration_seconds})
    tl.snapshots = snaps[-10:]
    tl.data = data
    flag_modified(tl, "data")
    tl.duration_seconds = data["duration"]
    tl.width, tl.height, tl.fps = doc.width, doc.height, doc.fps
    tl.version += 1
    tl.checksum = _checksum(data)
    db.flush()
    return tl


def apply_operation(doc: dict[str, Any], op: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Pure function applying an edit op to a timeline document. Used by the API's /ops endpoint."""
    tracks = doc.get("tracks", [])

    def find_clip(clip_id: str):
        for tr in tracks:
            for c in tr.get("clips", []):
                if c.get("id") == clip_id:
                    return tr, c
        raise ValueError(f"clip {clip_id} not found")

    if op == "trim_clip":
        _, c = find_clip(payload["clip_id"])
        if "trim_start" in payload:
            delta = float(payload["trim_start"]) - float(c.get("trim_start", 0))
            c["trim_start"] = max(0.0, float(payload["trim_start"]))
            c["duration"] = max(0.5, float(c["duration"]) - delta)
        if "duration" in payload:
            c["duration"] = max(0.5, float(payload["duration"]))
    elif op == "split_clip":
        tr, c = find_clip(payload["clip_id"])
        at = float(payload["at"])  # absolute time
        rel = at - float(c["start"])
        if 0.25 < rel < float(c["duration"]) - 0.25:
            right = json.loads(json.dumps(c))
            right["id"] = f"{c['id']}-{uuid.uuid4().hex[:6]}"
            right["start"] = at
            right["duration"] = float(c["duration"]) - rel
            right["trim_start"] = float(c.get("trim_start", 0)) + rel
            right["transition_in"] = {"type": "none", "duration": 0}
            c["duration"] = rel
            idx = tr["clips"].index(c)
            tr["clips"].insert(idx + 1, right)
    elif op == "set_volume":
        _, c = find_clip(payload["clip_id"])
        c["volume"] = max(0.0, min(3.0, float(payload["volume"])))
    elif op == "set_fade":
        _, c = find_clip(payload["clip_id"])
        if "fade_in" in payload:
            c["fade_in"] = max(0.0, float(payload["fade_in"]))
        if "fade_out" in payload:
            c["fade_out"] = max(0.0, float(payload["fade_out"]))
    elif op == "move_clip":
        _, c = find_clip(payload["clip_id"])
        c["start"] = max(0.0, float(payload["start"]))
    elif op == "delete_clip":
        tr, c = find_clip(payload["clip_id"])
        tr["clips"].remove(c)
    elif op == "set_transition":
        _, c = find_clip(payload["clip_id"])
        c["transition_in"] = {"type": payload.get("type", "fade"), "duration": float(payload.get("duration", 0.5))}
    elif op == "set_effect":
        _, c = find_clip(payload["clip_id"])
        c["effect"] = {"type": payload.get("type", "ken_burns"), "intensity": float(payload.get("intensity", 0.1))}
    elif op == "reorder_scenes":
        pass  # handled by the scene endpoint followed by sync_from_scenes
    else:
        raise ValueError(f"unknown op {op}")

    end = 0.0
    for tr in tracks:
        for c in tr.get("clips", []):
            end = max(end, float(c["start"]) + float(c["duration"]))
    doc["duration"] = round(end, 3)
    return doc
