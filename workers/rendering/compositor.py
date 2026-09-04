"""FFmpeg compositor: TimelineDocument -> MP4.

Strategy (robust for long videos and modest hardware):

1. **Per-clip render** - each visual clip on the scene track is rendered to an
   intermediate MP4 of exactly `clip.duration` seconds at the target size/fps:
   images get Ken Burns / zoom / pan via `zoompan`; videos are trimmed/looped and
   scaled with letterboxing; text-only clips (intro/outro) get a gradient card.
   Clips render in parallel (bounded by CPU) so a 60-minute video does not need
   a single gigantic filter graph.
2. **Transitions** - adjacent clips are joined with `xfade` in a streaming chain
   (clip N+1 overlaps the tail of N by the transition duration), falling back to
   concat when the transition is `none`. Total duration therefore equals the
   timeline duration minus the sum of overlaps; audio is time-shifted accordingly.
3. **Audio mix** - voiceover clips are placed with `adelay`, music is looped,
   faded and side-chain ducked under the narration, sfx are overlaid; the mix is
   loudness-normalised.
4. **Overlays** - text overlays are rendered with libass (ASS events, which also
   gives us fades/animations without `drawtext`), captions are burned in via a
   generated ASS file, the watermark is overlaid last.
5. **Mux** - final H.264/AAC MP4 with faststart.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services.caption_service import DEFAULT_STYLE, to_ass
from app.utils.ffmpeg import FFmpegError, escape_filter_path, ffmpeg_path, media_duration, run_ffmpeg
from app.utils.fonts import default_font_path, font_family_name
from workers.rendering.text_cards import render_text_card

log = get_logger(__name__)

XFADE_TYPES = {
    "fade": "fade",
    "dissolve": "dissolve",
    "wipeleft": "wipeleft",
    "wiperight": "wiperight",
    "slideleft": "slideleft",
    "slideright": "slideright",
    "circleopen": "circleopen",
    "fadeblack": "fadeblack",
    "fadewhite": "fadewhite",
    "smoothleft": "smoothleft",
    "smoothright": "smoothright",
}


@dataclass
class AssetLocator:
    """Resolves asset ids -> local file paths (downloads from object storage on demand)."""

    resolve: Callable[[str, str | None], Path | None]
    cache: dict[str, Path | None] = field(default_factory=dict)

    def path(self, asset_id: str | None, kind: str | None = None) -> Path | None:
        if not asset_id:
            return None
        if asset_id not in self.cache:
            self.cache[asset_id] = self.resolve(asset_id, kind)
        return self.cache[asset_id]


@dataclass
class RenderOptions:
    width: int
    height: int
    fps: int = 30
    crf: int = 20
    preset: str = "medium"
    burn_captions: bool = True
    watermark_text: str | None = None
    watermark_image: Path | None = None
    watermark_position: str = "bottom_right"
    watermark_opacity: float = 0.6
    range_start: float | None = None
    range_end: float | None = None
    is_preview: bool = False
    threads: int = 0
    max_parallel_clips: int = 2


class Compositor:
    def __init__(
        self,
        doc: dict[str, Any],
        *,
        locator: AssetLocator,
        options: RenderOptions,
        captions: list[dict] | None,
        caption_style: dict[str, Any] | None,
        work_dir: Path,
        progress: Callable[[float, str], None] | None = None,
        check_cancelled: Callable[[], None] | None = None,
    ):
        self.doc = doc
        self.locator = locator
        self.o = options
        self.captions = captions or []
        self.caption_style = {**DEFAULT_STYLE, **(doc.get("captions") or {}), **(caption_style or {})}
        self.work = work_dir
        self.work.mkdir(parents=True, exist_ok=True)
        self.progress = progress or (lambda f, m: None)
        self.check_cancelled = check_cancelled or (lambda: None)
        self.tracks: dict[str, list[dict[str, Any]]] = {t: [] for t in ("video", "image", "voiceover", "music", "sfx", "text", "captions")}
        for t in doc.get("tracks", []):
            self.tracks.setdefault(t["kind"], []).append(t)

    # ------------------------------------------------------------------ public
    def render(self, output: Path) -> dict[str, Any]:
        visual_clips = self._visual_clips()
        if not visual_clips:
            raise FFmpegError("Timeline has no visual clips to render")
        if self.o.range_start is not None or self.o.range_end is not None:
            visual_clips = self._apply_range(visual_clips)
        self.progress(0.02, "Rendering video... preparing clips")

        clip_files = self._render_clips(visual_clips)  # 2% -> 55%
        self.check_cancelled()
        video_path, offsets, total = self._join_clips(visual_clips, clip_files)  # 55% -> 75%
        self.check_cancelled()
        audio_path = self._mix_audio(total, offsets)  # 75% -> 85%
        self.check_cancelled()
        final = self._finalize(video_path, audio_path, total, offsets, output)  # 85% -> 100%
        return {"path": str(final), "duration": round(total, 3), "width": self.o.width, "height": self.o.height, "fps": self.o.fps}

    # ------------------------------------------------------------------ helpers
    def _visual_clips(self) -> list[dict]:
        clips: list[dict] = []
        for tr in self.tracks.get("video", []) + self.tracks.get("image", []):
            if tr.get("muted"):
                continue
            clips.extend(tr.get("clips", []))
        clips.sort(key=lambda c: float(c["start"]))
        return clips

    def _apply_range(self, clips: list[dict]) -> list[dict]:
        rs = float(self.o.range_start or 0)
        re_ = float(self.o.range_end or 1e9)
        out = []
        for c in clips:
            s, d = float(c["start"]), float(c["duration"])
            if s + d <= rs or s >= re_:
                continue
            c2 = dict(c)
            new_start = max(s, rs)
            new_end = min(s + d, re_)
            c2["trim_start"] = float(c.get("trim_start", 0)) + (new_start - s)
            c2["start"] = new_start - rs
            c2["duration"] = new_end - new_start
            out.append(c2)
        self._range_offset = rs
        return out

    # -- stage 1: per-clip renders ------------------------------------------------
    def _render_clips(self, clips: list[dict]) -> list[Path]:
        outputs: list[Path | None] = [None] * len(clips)
        n = len(clips)
        done = 0

        # Resolve (and download) every asset on the calling thread first: the locator may
        # use a DB session, which must never be shared across worker threads.
        self.progress(0.02, "Rendering video... fetching assets")
        for c in clips:
            if c.get("asset_id"):
                self.locator.path(c["asset_id"], c.get("asset_kind"))

        def work(i: int, clip: dict) -> tuple[int, Path]:
            out = self.work / f"clip_{i:04d}.mp4"
            if not out.exists():
                self._render_single_clip(clip, out)
            return i, out

        max_workers = max(1, min(self.o.max_parallel_clips, os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(work, i, c) for i, c in enumerate(clips)]
            for fut in as_completed(futures):
                i, path = fut.result()
                outputs[i] = path
                done += 1
                self.check_cancelled()
                self.progress(0.02 + 0.53 * done / n, f"Rendering video... clip {done}/{n}")
        return [p for p in outputs if p is not None]

    def _render_single_clip(self, clip: dict, out: Path) -> None:
        W, H, fps = self.o.width, self.o.height, self.o.fps
        duration = max(0.1, float(clip["duration"]))
        asset_kind = clip.get("asset_kind")
        src = self.locator.path(clip.get("asset_id"), asset_kind) if clip.get("asset_id") else None
        effect = (clip.get("effect") or {}).get("type", "ken_burns")
        intensity = float((clip.get("effect") or {}).get("intensity", 0.12))
        enc = self._encoder_args(fast=True)

        if src is None or asset_kind == "text":
            card = self.work / f"{out.stem}_card.png"
            if not card.exists():
                render_text_card(card, W, H, title=clip.get("label") or "", subtitle=None, seed=clip.get("id", "x"))
            src, asset_kind = card, "image"

        if asset_kind == "image" or str(src).lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            vf = self._image_motion_filter(effect, intensity, duration, W, H, fps)
            args = ["-loop", "1", "-framerate", str(fps), "-i", str(src), "-t", f"{duration:.3f}", "-vf", vf, "-r", str(fps), *enc, "-an", str(out)]
        else:
            trim_start = float(clip.get("trim_start", 0) or 0)
            src_dur = media_duration(src) or duration
            avail = max(0.0, src_dur - trim_start)
            scale = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
            if avail + 0.05 < duration:
                # Loop short clips to fill the scene duration
                loops = math.ceil(duration / max(0.5, src_dur))
                args = ["-stream_loop", str(loops), "-i", str(src), "-t", f"{duration:.3f}", "-vf", f"{scale},fps={fps}", *enc, "-an", str(out)]
            else:
                args = ["-ss", f"{trim_start:.3f}", "-i", str(src), "-t", f"{duration:.3f}", "-vf", f"{scale},fps={fps}", *enc, "-an", str(out)]
        run_ffmpeg(args, timeout=max(120, int(duration * 20)))

    def _image_motion_filter(self, effect: str, intensity: float, duration: float, W: int, H: int, fps: int) -> str:
        frames = max(1, int(round(duration * fps)))
        zmax = 1.0 + max(0.02, min(0.5, intensity * 1.6))
        # Upscale first so zoompan has sub-pixel headroom (avoids jitter), then animate.
        pre = f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2}"
        step = (zmax - 1.0) / frames
        if effect == "none":
            return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,format=yuv420p"
        if effect == "zoom_in":
            z, x, y = f"min(1+{step:.6f}*on,{zmax:.4f})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif effect == "zoom_out":
            z, x, y = f"max({zmax:.4f}-{step:.6f}*on,1.0)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif effect == "pan_left":
            z, x, y = f"{zmax:.4f}", f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-(ih/zoom/2)"
        elif effect == "pan_right":
            z, x, y = f"{zmax:.4f}", f"(iw-iw/zoom)*(on/{frames})", "ih/2-(ih/zoom/2)"
        elif effect == "pan_up":
            z, x, y = f"{zmax:.4f}", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{frames})"
        elif effect == "pan_down":
            z, x, y = f"{zmax:.4f}", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(on/{frames})"
        else:  # ken_burns: slow zoom with a gentle diagonal drift
            z = f"min(1+{step:.6f}*on,{zmax:.4f})"
            x = f"(iw-iw/zoom)*(0.5+0.5*sin(on/{frames}*1.2))"
            y = f"(ih-ih/zoom)*(0.5-0.5*cos(on/{frames}*0.9))"
        return f"{pre},zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={fps},setsar=1,format=yuv420p"

    # -- stage 2: transitions -----------------------------------------------------
    def _join_clips(self, clips: list[dict], files: list[Path]) -> tuple[Path, list[float], float]:
        """Chain clips with xfade. Returns (video_path, per-clip start offsets in output time, total)."""
        n = len(files)
        offsets: list[float] = []
        cur_total = 0.0
        transitions: list[tuple[str, float]] = []
        for i, c in enumerate(clips):
            d = float(c["duration"])
            tr = c.get("transition_in") or {}
            ttype = XFADE_TYPES.get(str(tr.get("type", "none")))
            tdur = float(tr.get("duration", 0) or 0)
            if i == 0 or not ttype or tdur <= 0.05:
                ttype, tdur = None, 0.0
            tdur = min(tdur, d * 0.45, float(clips[i - 1]["duration"]) * 0.45) if i > 0 else 0.0
            start = cur_total - tdur if ttype else cur_total
            offsets.append(round(max(0.0, start), 3))
            cur_total = start + d
            transitions.append((ttype or "", tdur))
        total = cur_total

        if n == 1:
            return files[0], offsets, total

        # Chain in batches to keep filter graphs small (xfade needs the whole chain in one graph,
        # so we join in groups of 12 and then join the groups).
        BATCH = 12
        group_files: list[Path] = []
        group_specs: list[tuple[list[Path], list[tuple[str, float]]]] = []
        for gi in range(0, n, BATCH):
            group_specs.append((files[gi : gi + BATCH], transitions[gi : gi + BATCH]))
        for gi, (gfiles, gtrans) in enumerate(group_specs):
            out = self.work / f"group_{gi:03d}.mp4"
            self._xfade_chain(gfiles, gtrans, out)
            group_files.append(out)
            self.check_cancelled()
            self.progress(0.55 + 0.18 * (gi + 1) / len(group_specs), f"Rendering video... transitions {gi + 1}/{len(group_specs)}")
        if len(group_files) == 1:
            return group_files[0], offsets, total
        # Join groups: the first transition of each group (index 0 within the group) applies between groups
        joined = self.work / "joined.mp4"
        inter_trans = [("", 0.0)] + [group_specs[g][1][0] for g in range(1, len(group_specs))]
        self._xfade_chain(group_files, inter_trans, joined)
        return joined, offsets, total

    def _xfade_chain(self, files: list[Path], transitions: list[tuple[str, float]], out: Path) -> None:
        if len(files) == 1:
            shutil.copyfile(files[0], out)
            return
        durations = [media_duration(f) for f in files]
        args: list[str] = []
        for f in files:
            args += ["-i", str(f)]
        graph = []
        prev = "[0:v]"
        offset = durations[0]
        for i in range(1, len(files)):
            ttype, tdur = transitions[i]
            label = f"[v{i}]" if i < len(files) - 1 else "[vout]"
            if ttype and tdur > 0.05:
                off = max(0.0, offset - tdur)
                graph.append(f"{prev}[{i}:v]xfade=transition={ttype}:duration={tdur:.3f}:offset={off:.3f}{label}")
                offset = off + durations[i]
            else:
                # No transition: hard cut via concat filter
                graph.append(f"{prev}[{i}:v]concat=n=2:v=1:a=0{label}")
                offset = offset + durations[i]
            prev = label
        args += ["-filter_complex", ";".join(graph), "-map", "[vout]", *self._encoder_args(fast=True), "-an", str(out)]
        run_ffmpeg(args, timeout=max(300, int(sum(durations) * 15)))

    # -- stage 3: audio -------------------------------------------------------------
    def _mix_audio(self, total: float, offsets: list[float]) -> Path | None:
        """Mix voiceover, music and sfx into a single AAC track of `total` seconds."""
        visual_clips = self._visual_clips()
        if self.o.range_start is not None or self.o.range_end is not None:
            visual_clips = self._apply_range(visual_clips)
        # Map timeline time -> output time (transitions shrink the output). Use scene offsets.
        tl_starts = [float(c["start"]) for c in visual_clips]

        def map_time(t: float) -> float:
            # piecewise: find clip containing t
            for i in range(len(tl_starts)):
                s = tl_starts[i]
                e = s + float(visual_clips[i]["duration"])
                if s <= t < e or i == len(tl_starts) - 1:
                    return offsets[i] + (t - s)
            return t

        inputs: list[str] = []
        filters: list[str] = []
        mix_labels: list[str] = []
        idx = 0

        range_off = getattr(self, "_range_offset", 0.0)

        def add_clip(clip: dict, kind: str) -> None:
            nonlocal idx
            path = self.locator.path(clip.get("asset_id"), "voiceover" if kind == "voiceover" else "audio")
            if not path or not path.exists():
                return
            start = float(clip["start"]) - range_off
            dur = float(clip["duration"])
            if start + dur <= 0 or start >= total + 5:
                return
            trim_start = float(clip.get("trim_start", 0) or 0)
            if start < 0:
                trim_start += -start
                dur += start
                start = 0.0
            out_start = map_time(start) if kind == "voiceover" else start
            vol = float(clip.get("volume", 1.0))
            fi, fo = float(clip.get("fade_in", 0) or 0), float(clip.get("fade_out", 0) or 0)
            src_dur = media_duration(path) or dur
            loop_args: list[str] = []
            if kind == "music" and src_dur + 0.1 < dur:
                loop_args = ["-stream_loop", str(math.ceil(dur / max(1.0, src_dur)))]
            inputs.extend([*loop_args, "-i", str(path)])
            chain = [f"atrim=start={trim_start:.3f}:duration={dur:.3f}", "asetpts=PTS-STARTPTS", "aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
            if fi > 0:
                chain.append(f"afade=t=in:st=0:d={fi:.3f}")
            if fo > 0:
                chain.append(f"afade=t=out:st={max(0.0, dur - fo):.3f}:d={fo:.3f}")
            chain.append(f"volume={vol:.3f}")
            delay_ms = int(round(out_start * 1000))
            chain.append(f"adelay={delay_ms}|{delay_ms}")
            label = f"[a{idx}]"
            filters.append(f"[{idx}:a]{','.join(chain)}{label}")
            mix_labels.append((kind, label))
            idx += 1

        for tr in self.tracks.get("voiceover", []):
            if tr.get("muted"):
                continue
            for c in tr.get("clips", []):
                add_clip({**c, "volume": float(c.get("volume", 1.0)) * float(tr.get("volume", 1.0))}, "voiceover")
        for tr in self.tracks.get("music", []):
            if tr.get("muted"):
                continue
            for c in tr.get("clips", []):
                add_clip({**c, "volume": float(c.get("volume", 0.15)) * float(tr.get("volume", 1.0))}, "music")
        for tr in self.tracks.get("sfx", []):
            if tr.get("muted"):
                continue
            for c in tr.get("clips", []):
                add_clip({**c, "volume": float(c.get("volume", 0.8)) * float(tr.get("volume", 1.0))}, "sfx")

        if not mix_labels:
            return None

        voice = [lbl for k, lbl in mix_labels if k == "voiceover"]
        music = [lbl for k, lbl in mix_labels if k == "music"]
        sfx = [lbl for k, lbl in mix_labels if k == "sfx"]

        def mix(labels: list[str], out_label: str) -> None:
            if len(labels) == 1:
                filters.append(f"{labels[0]}anull{out_label}")
            else:
                filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0{out_label}")

        final_parts = []
        if voice:
            mix(voice, "[voice]")
            final_parts.append("[voice]")
        if music:
            mix(music, "[musicmix]")
            if voice:
                # Side-chain duck music under narration
                filters.append("[voice]asplit=2[voice_main][voice_sc]")
                filters.append("[musicmix][voice_sc]sidechaincompress=threshold=0.02:ratio=8:attack=40:release=600:makeup=1[music_ducked]")
                final_parts = ["[voice_main]", "[music_ducked]"]
            else:
                final_parts.append("[musicmix]")
        if sfx:
            mix(sfx, "[sfxmix]")
            final_parts.append("[sfxmix]")

        if len(final_parts) == 1:
            filters.append(f"{final_parts[0]}anull[premix]")
        else:
            filters.append(f"{''.join(final_parts)}amix=inputs={len(final_parts)}:duration=longest:normalize=0[premix]")
        filters.append(f"[premix]apad,atrim=0:{total:.3f},loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95[aout]")

        out = self.work / "audio_mix.m4a"
        args = [*inputs, "-filter_complex", ";".join(filters), "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)]
        self.progress(0.76, "Rendering video... mixing audio")
        run_ffmpeg(args, timeout=max(300, int(total * 6)))
        self.progress(0.85, "Rendering video... audio mixed")
        return out

    # -- stage 4: overlays + mux ------------------------------------------------------
    def _finalize(self, video: Path, audio: Path | None, total: float, offsets: list[float], output: Path) -> Path:
        W, H = self.o.width, self.o.height
        filters: list[str] = []
        inputs = ["-i", str(video)]
        if audio:
            inputs += ["-i", str(audio)]

        # Text overlays -> ASS (fade/slide animations supported by libass)
        overlays = self._text_overlays_ass(offsets)
        if overlays:
            ass_path = self.work / "overlays.ass"
            ass_path.write_text(overlays, encoding="utf-8")
            filters.append(f"ass='{escape_filter_path(ass_path)}':fontsdir='{escape_filter_path(Path(default_font_path() or '.').parent)}'")

        # Captions
        if self.o.burn_captions and self.captions and self.caption_style.get("enabled", True):
            cues = self._remap_cues(self.captions, offsets)
            if cues:
                ass = to_ass(cues, {**self.caption_style, "font_family": self.caption_style.get("font_family") or font_family_name()}, W, H)
                cap_path = self.work / "captions.ass"
                cap_path.write_text(ass, encoding="utf-8")
                filters.append(f"ass='{escape_filter_path(cap_path)}':fontsdir='{escape_filter_path(Path(default_font_path() or '.').parent)}'")

        # Watermark
        wm_filter_inputs = 0
        if self.o.watermark_image and self.o.watermark_image.exists():
            inputs += ["-i", str(self.o.watermark_image)]
            wm_filter_inputs = 1
        elif self.o.watermark_text:
            wm_png = self.work / "watermark.png"
            from workers.rendering.text_cards import render_watermark

            render_watermark(wm_png, self.o.watermark_text, max(24, H // 36))
            inputs += ["-i", str(wm_png)]
            wm_filter_inputs = 1

        vf_chain = ",".join(filters) if filters else "null"
        graph = [f"[0:v]{vf_chain}[vbase]"]
        last = "[vbase]"
        if wm_filter_inputs:
            wm_idx = 2 if audio else 1
            margin = max(16, W // 60)
            pos = {
                "top_left": f"{margin}:{margin}",
                "top_right": f"W-w-{margin}:{margin}",
                "bottom_left": f"{margin}:H-h-{margin}",
                "bottom_right": f"W-w-{margin}:H-h-{margin}",
            }.get(self.o.watermark_position, f"W-w-{margin}:H-h-{margin}")
            graph.append(f"[{wm_idx}:v]format=rgba,colorchannelmixer=aa={self.o.watermark_opacity:.2f},scale={max(64, W // 8)}:-1[wm]")
            graph.append(f"[vbase][wm]overlay={pos}[vout]")
            last = "[vout]"

        args = [*inputs, "-filter_complex", ";".join(graph), "-map", last]
        if audio:
            args += ["-map", "1:a", "-c:a", "copy"]
        args += [*self._encoder_args(fast=False), "-movflags", "+faststart", "-t", f"{total:.3f}", str(output)]

        def on_prog(frac: float) -> None:
            self.progress(0.86 + 0.13 * frac, f"Rendering video... encoding {int(frac * 100)}%")

        run_ffmpeg(args, timeout=max(600, int(total * 30)), on_progress=on_prog, total_duration=total)
        self.progress(0.995, "Rendering video... finalising")
        return output

    def _text_overlays_ass(self, offsets: list[float]) -> str | None:
        clips = [c for tr in self.tracks.get("text", []) if not tr.get("muted") for c in tr.get("clips", []) if (c.get("text") or {}).get("content")]
        if not clips:
            return None
        W, H = self.o.width, self.o.height
        scale = H / 1080.0
        font = font_family_name()
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Overlay,{font},{int(56 * scale)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{2 * scale:.1f},{1 * scale:.1f},5,{int(80 * scale)},{int(80 * scale)},{int(80 * scale)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        align_map = {"top": 8, "center": 5, "bottom": 2, "top_left": 7, "top_right": 9, "bottom_left": 1, "bottom_right": 3}
        range_off = getattr(self, "_range_offset", 0.0)
        lines = []
        for c in clips:
            t = c["text"]
            start = self._map_time(float(c["start"]) - range_off, offsets)
            end = start + float(c["duration"])
            if end <= 0:
                continue
            size = int(float(t.get("font_size", 56)) * scale)
            color = _ass_hex(t.get("color", "#FFFFFF"))
            align = align_map.get(t.get("position", "center"), 5)
            anim = t.get("animation", "fade")
            tags = f"{{\\an{align}\\fs{size}\\c{color}\\bord{2 * scale:.1f}\\shad{1 * scale:.1f}"
            if t.get("background"):
                tags += f"\\3c{_ass_hex(t['background'])}\\bord{6 * scale:.1f}\\shad0"
            if anim == "fade":
                tags += "\\fad(300,300)"
            elif anim == "slide_up":
                # move from slightly below to final position (only for center-ish alignments use \move)
                tags += "\\fad(200,200)"
            elif anim == "typewriter":
                tags += "\\fad(100,300)"
            tags += "}"
            text = str(t["content"]).replace("\n", "\\N")
            if anim == "typewriter":
                # reveal by karaoke timing across the first 60% of the clip
                words = text.split(" ")
                per = max(1, int((end - start) * 0.6 * 100 / max(1, len(words))))
                text = "".join(f"{{\\k{per}}}{w} " for w in words).strip()
            lines.append(f"Dialogue: 1,{_ass_ts(max(0, start))},{_ass_ts(end)},Overlay,,0,0,0,,{tags}{text}")
        return header + "\n".join(lines) + "\n"

    def _remap_cues(self, cues: list[dict], offsets: list[float]) -> list[dict]:
        range_off = getattr(self, "_range_offset", 0.0)
        out = []
        for c in cues:
            s = self._map_time(float(c["start"]) - range_off, offsets)
            e = self._map_time(float(c["end"]) - range_off, offsets)
            if e <= 0:
                continue
            words = [{**w, "start": self._map_time(float(w["start"]) - range_off, offsets), "end": self._map_time(float(w["end"]) - range_off, offsets)} for w in c.get("words", [])]
            out.append({**c, "start": max(0.0, s), "end": max(0.1, e), "words": words})
        return out

    def _map_time(self, t: float, offsets: list[float]) -> float:
        clips = self._visual_clips()
        if self.o.range_start is not None or self.o.range_end is not None:
            clips = self._apply_range(clips)
        for i, c in enumerate(clips):
            s = float(c["start"])
            e = s + float(c["duration"])
            if s <= t < e or i == len(clips) - 1:
                return offsets[i] + (t - s)
        return t

    def _encoder_args(self, *, fast: bool) -> list[str]:
        preset = "veryfast" if (fast or self.o.is_preview) else self.o.preset
        crf = min(28, self.o.crf + 4) if (fast or self.o.is_preview) else self.o.crf
        args = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2" if self.o.height <= 1080 else "5.1", "-g", str(self.o.fps * 2)]
        if self.o.threads:
            args += ["-threads", str(self.o.threads)]
        return args


def _ass_hex(hex_color: str) -> str:
    h = (hex_color or "#FFFFFF").lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}&"


def _ass_ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{int(round((s - int(s)) * 100)):02d}"


def generate_thumbnail(video: Path, out: Path, at: float = 1.0, width: int = 1280) -> Path:
    run_ffmpeg(["-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(out)], timeout=120)
    return out


__all__ = ["Compositor", "RenderOptions", "AssetLocator", "generate_thumbnail", "ffmpeg_path", "json", "subprocess", "tempfile", "settings"]
