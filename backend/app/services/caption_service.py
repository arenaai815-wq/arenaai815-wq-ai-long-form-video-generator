"""Captions: build cues from per-scene word timings (or STT), export SRT/VTT/ASS."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.enums import UsageKind
from app.models.media import Caption, Voiceover
from app.models.project import Project
from app.models.scene import Scene
from app.models.user import User
from app.providers import get_registry
from app.services.billing_service import record_usage_sync
from app.services.media_service import default_local_path
from app.services.scene_service import scene_start_times
from app.storage import get_storage
from app.storage.base import build_key
from app.utils.text import split_sentences

DEFAULT_STYLE: dict[str, Any] = {
    "enabled": True,
    "burn_in": True,
    "font_family": "DejaVu Sans",
    "font_size": 44,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "background_color": None,
    "position": "bottom",
    "margin_v": 60,
    "animation": "none",
    "max_chars_per_line": 42,
    "max_lines": 2,
    "timing_offset": 0.0,
    "highlight_color": "#FFD400",
}


# ------------------------------------------------------------------ cue building


def _group_words(words: list[dict], max_chars: int, max_lines: int, max_duration: float = 6.0) -> list[list[dict]]:
    """Group words into caption blocks respecting line length, line count and duration."""
    limit = max_chars * max_lines
    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_len = 0
    for w in words:
        wl = len(w["word"])
        too_long = cur and (cur_len + 1 + wl > limit)
        too_slow = cur and (w["end"] - cur[0]["start"] > max_duration)
        ends_sentence = cur and re.search(r"[.!?]$", cur[-1]["word"] or "")
        if too_long or too_slow or (ends_sentence and cur_len > max_chars * 0.6):
            groups.append(cur)
            cur, cur_len = [], 0
        cur.append(w)
        cur_len += wl + (1 if cur_len else 0)
    if cur:
        groups.append(cur)
    return groups


def font_scale(width: int, height: int) -> float:
    """Font scale factor relative to the 1920x1080 reference frame (styles are authored at 1080p)."""
    return (height if width >= height else width) / 1080.0


def chars_per_line_for(width: int, height: int, base_chars: int) -> int:
    """Line length budget for a frame: `base_chars` is defined for 16:9; narrower frames get
    proportionally fewer characters so wrapped lines stay inside the safe area."""
    ratio = (width / height) / (16 / 9)
    return max(16, int(round(base_chars * min(1.0, ratio))))


def wrap_lines(text: str, max_chars: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:  # balance into max_lines chunks
        per = -(-len(words) // max_lines)
        lines = [" ".join(words[i : i + per]) for i in range(0, len(words), per)][:max_lines]
    return lines


def cues_from_scene_timings(
    scenes: list[Scene],
    voiceovers: dict[uuid.UUID, Voiceover],
    *,
    max_chars: int,
    max_lines: int,
    offset: float = 0.0,
) -> list[dict[str, Any]]:
    starts = scene_start_times(scenes)
    cues: list[dict[str, Any]] = []
    idx = 1
    for scene in sorted(scenes, key=lambda s: s.order_index):
        base = starts[scene.id] + offset
        vo = voiceovers.get(scene.id)
        if vo and vo.word_timings:
            words = [{"word": w["word"], "start": base + float(w["start"]), "end": base + float(w["end"])} for w in vo.word_timings]
        else:
            # No timings: distribute narration sentences evenly over the scene duration
            sentences = split_sentences(scene.narration) or ([scene.narration] if scene.narration else [])
            total_chars = sum(len(s) for s in sentences) or 1
            t = base
            words = []
            for s in sentences:
                d = float(scene.duration_seconds) * len(s) / total_chars
                ws = s.split()
                if not ws:
                    continue
                per = d / len(ws)
                for i, w in enumerate(ws):
                    words.append({"word": w, "start": t + i * per, "end": t + (i + 1) * per})
                t += d
        for group in _group_words(words, max_chars, max_lines):
            text = " ".join(w["word"] for w in group)
            cues.append(
                {
                    "index": idx,
                    "start": round(group[0]["start"], 3),
                    "end": round(max(group[-1]["end"], group[0]["start"] + 0.8), 3),
                    "text": text,
                    "scene_id": str(scene.id),
                    "words": [{"word": w["word"], "start": round(w["start"], 3), "end": round(w["end"], 3)} for w in group],
                }
            )
            idx += 1
    # Ensure cues never overlap
    for a, b in zip(cues, cues[1:], strict=False):
        if a["end"] > b["start"]:
            a["end"] = round(max(a["start"] + 0.3, b["start"] - 0.05), 3)
    return cues


# ------------------------------------------------------------------ formats


def _ts_srt(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def _ts_vtt(t: float) -> str:
    return _ts_srt(t).replace(",", ".")


def _ts_ass(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{int(round((s - int(s)) * 100)):02d}"


def to_srt(cues: list[dict], max_chars: int = 42, max_lines: int = 2) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{_ts_srt(c['start'])} --> {_ts_srt(c['end'])}\n" + "\n".join(wrap_lines(c["text"], max_chars, max_lines)) + "\n")
    return "\n".join(out)


def to_vtt(cues: list[dict], max_chars: int = 42, max_lines: int = 2) -> str:
    out = ["WEBVTT", ""]
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{_ts_vtt(c['start'])} --> {_ts_vtt(c['end'])}\n" + "\n".join(wrap_lines(c["text"], max_chars, max_lines)) + "\n")
    return "\n".join(out)


def _ass_color(hex_color: str | None, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR"""
    if not hex_color:
        return f"&H{alpha:02X}000000"
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def to_ass(cues: list[dict], style: dict[str, Any], width: int, height: int) -> str:
    """Advanced SubStation Alpha with styling + optional animation (fade / pop / karaoke)."""
    st = {**DEFAULT_STYLE, **(style or {})}
    align = {"bottom": 2, "center": 5, "top": 8}[st.get("position", "bottom")]
    # Scale font relative to a 1080p *landscape* frame so styling looks the same at any
    # resolution. Portrait / square frames scale by width (the short side) - scaling by height
    # would make 9:16 captions ~1.8x too big and overflow the frame.
    scale = font_scale(width, height)
    font_size = int(round(float(st["font_size"]) * scale))
    margin_v = int(round(float(st["margin_v"]) * scale))
    outline = float(st.get("outline_width") or 0) * scale
    bg = st.get("background_color")
    border_style = 4 if bg else 1  # 4 = opaque box behind text (libass), 1 = outline+shadow
    back_colour = _ass_color(bg, 0x60) if bg else _ass_color("#000000", 0x80)
    max_chars, max_lines = chars_per_line_for(width, height, int(st["max_chars_per_line"])), int(st["max_lines"])
    anim = st.get("animation", "none")
    highlight = _ass_color(st.get("highlight_color", "#FFD400"))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{st['font_family']},{font_size},{_ass_color(st['color'])},{highlight},{_ass_color(st['outline_color'])},{back_colour},-1,0,0,0,100,100,0,0,{border_style},{outline:.1f},{1 if not bg else 0},{align},{int(60 * scale)},{int(60 * scale)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for c in cues:
        text_lines = wrap_lines(c["text"], max_chars, max_lines)
        tag = ""
        if anim == "fade":
            tag = "{\\fad(150,150)}"
        elif anim == "pop":
            tag = "{\\fad(80,80)\\fscx80\\fscy80\\t(0,120,\\fscx100\\fscy100)}"
        if anim == "karaoke" and c.get("words"):
            # \k durations are in centiseconds relative to the cue start
            parts = []
            cursor = c["start"]
            for w in c["words"]:
                gap = max(0.0, w["start"] - cursor)
                if gap > 0.02:
                    parts.append(f"{{\\k{int(gap * 100)}}}")
                parts.append(f"{{\\k{int(max(0.01, w['end'] - w['start']) * 100)}}}{w['word']} ")
                cursor = w["end"]
            body = "".join(parts).strip()
            # rewrap karaoke text roughly by inserting \N after max_chars visible chars
            visible, out, count = re.sub(r"\{[^}]*\}", "", body), [], 0
            if len(visible) > max_chars:
                tokens = body.split(" ")
                acc = ""
                for tkn in tokens:
                    plain = re.sub(r"\{[^}]*\}", "", tkn)
                    if count + len(plain) > max_chars and acc:
                        out.append(acc.strip())
                        acc, count = "", 0
                    acc += tkn + " "
                    count += len(plain) + 1
                if acc:
                    out.append(acc.strip())
                body = "\\N".join(out[:max_lines])
            text = body
        else:
            text = "\\N".join(text_lines)
        lines.append(f"Dialogue: 0,{_ts_ass(c['start'])},{_ts_ass(c['end'])},Default,,0,0,0,,{tag}{text}")
    return header + "\n".join(lines) + "\n"


# ------------------------------------------------------------------ service


def generate_captions_sync(
    db: Session,
    project: Project,
    user: User,
    scenes: list[Scene],
    voiceovers: dict[uuid.UUID, Voiceover],
    *,
    mode: str = "auto",
    language: str | None = None,
    style: dict[str, Any] | None = None,
    job_id=None,
    progress: Callable[[float, str], None] | None = None,
) -> Caption:
    st = {**DEFAULT_STYLE, **((project.settings or {}).get("captions") or {}), **(style or {})}
    max_chars, max_lines = int(st["max_chars_per_line"]), int(st["max_lines"])
    lang = language or project.language or "en"
    source = "tts_timings"
    provider_name = None

    has_timings = any(voiceovers.get(s.id) and voiceovers[s.id].word_timings for s in scenes)
    use_stt = mode == "transcribe" or (mode == "auto" and not has_timings and voiceovers)
    if use_stt:
        # Transcribe/align each scene's audio to get precise word timings
        stt = get_registry().stt()
        provider_name = stt.name
        source = "transcription"
        storage = get_storage()
        n = len(scenes) or 1
        for i, scene in enumerate(scenes):
            vo = voiceovers.get(scene.id)
            if not vo or not vo.storage_key:
                continue
            local = default_local_path(vo.storage_key)
            audio = local.read_bytes() if local else storage.get_bytes(vo.storage_key)
            res = stt.transcribe(audio, content_type=vo.content_type, language=lang, prompt=scene.narration)
            words = [{"word": w.word, "start": w.start, "end": w.end} for seg in res.segments for w in seg.words]
            if words:
                vo.word_timings = words
            record_usage_sync(db, user, UsageKind.STT_SECONDS, res.usage.seconds or (vo.duration_seconds or 0), "seconds", metrics=res.usage, project_id=project.id, job_id=job_id, charge=False)
            if progress:
                progress(0.1 + 0.7 * (i + 1) / n, f"Generating captions... aligning {i + 1}/{n}")
        db.flush()

    cues = cues_from_scene_timings(scenes, voiceovers, max_chars=max_chars, max_lines=max_lines, offset=float(st.get("timing_offset") or 0))
    if progress:
        progress(0.85, "Generating captions... writing SRT/VTT")

    db.execute(update(Caption).where(Caption.project_id == project.id).values(is_current=False))
    caption = Caption(
        project_id=project.id,
        language=lang,
        cues=cues,
        style=st,
        source=source,
        provider=provider_name,
        is_current=True,
        cue_count=len(cues),
    )
    db.add(caption)
    db.flush()
    write_caption_files(caption, user.id, project.id)
    return caption


def write_caption_files(caption: Caption, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
    storage = get_storage()
    st = {**DEFAULT_STYLE, **(caption.style or {})}
    mc, ml = int(st["max_chars_per_line"]), int(st["max_lines"])
    srt_key = build_key(owner_id, "captions", "captions.srt", project_id)
    vtt_key = build_key(owner_id, "captions", "captions.vtt", project_id)
    storage.put_bytes(srt_key, to_srt(caption.cues, mc, ml).encode("utf-8"), "application/x-subrip")
    storage.put_bytes(vtt_key, to_vtt(caption.cues, mc, ml).encode("utf-8"), "text/vtt")
    caption.srt_storage_key = srt_key
    caption.vtt_storage_key = vtt_key


def current_caption(db: Session, project_id: uuid.UUID) -> Caption | None:
    return db.execute(select(Caption).where(Caption.project_id == project_id, Caption.is_current.is_(True)).order_by(Caption.created_at.desc())).scalars().first()
