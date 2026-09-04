"""FFmpeg/ffprobe discovery and thin subprocess helpers used by workers and mocks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_FFMPEG: str | None = None
_FFPROBE: str | None = None


def ffmpeg_path() -> str:
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    candidates = [settings.ffmpeg_binary, os.environ.get("FFMPEG_BINARY"), shutil.which("ffmpeg")]
    for c in candidates:
        if c and Path(c).exists():
            _FFMPEG = c
            return c
    try:  # bundled static build (dev / CI convenience)
        import imageio_ffmpeg

        _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
        return _FFMPEG
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("ffmpeg binary not found. Install ffmpeg or set FFMPEG_BINARY.") from exc


def ffprobe_path() -> str | None:
    global _FFPROBE
    if _FFPROBE:
        return _FFPROBE
    for c in [settings.ffprobe_binary, os.environ.get("FFPROBE_BINARY"), shutil.which("ffprobe")]:
        if c and Path(c).exists():
            _FFPROBE = c
            return c
    sibling = Path(ffmpeg_path()).with_name("ffprobe")
    if sibling.exists():
        _FFPROBE = str(sibling)
        return _FFPROBE
    return None


class FFmpegError(RuntimeError):
    pass


def run_ffmpeg(
    args: list[str],
    *,
    timeout: int | None = None,
    on_progress: Callable[[float], None] | None = None,
    total_duration: float | None = None,
    cwd: str | Path | None = None,
) -> None:
    """Run ffmpeg, optionally reporting progress (0-1) parsed from `-progress pipe:1`."""
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-nostdin"]
    if on_progress:
        cmd += ["-progress", "pipe:1", "-stats_period", "0.5"]
    cmd += args
    log.debug("ffmpeg", cmd=" ".join(cmd[:12]) + (" ..." if len(cmd) > 12 else ""))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    stderr_chunks: list[str] = []
    try:
        if on_progress and proc.stdout is not None:
            for line in proc.stdout:
                if line.startswith("out_time_ms=") or line.startswith("out_time_us="):
                    try:
                        micros = int(line.split("=", 1)[1].strip() or 0)
                    except ValueError:
                        continue
                    if total_duration and total_duration > 0:
                        on_progress(min(1.0, max(0.0, micros / 1_000_000 / total_duration)))
        _, err = proc.communicate(timeout=timeout)
        if err:
            stderr_chunks.append(err)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise FFmpegError(f"ffmpeg timed out after {timeout}s") from exc
    if proc.returncode != 0:
        raise FFmpegError("".join(stderr_chunks)[-4000:] or f"ffmpeg exited with {proc.returncode}")


def probe(path: str | Path) -> dict:
    """Return ffprobe JSON (streams + format). Falls back to ffmpeg parsing if ffprobe is absent."""
    fp = ffprobe_path()
    if fp:
        out = subprocess.run(
            [fp, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout)
    # Fallback: parse `ffmpeg -i` banner
    out = subprocess.run([ffmpeg_path(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    info: dict = {"streams": [], "format": {}}
    import re

    m = re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", out.stderr)
    if m:
        h, mi, s = m.groups()
        info["format"]["duration"] = str(int(h) * 3600 + int(mi) * 60 + float(s))
    for sm in re.finditer(r"Stream #\d+:\d+.*?: (Video|Audio): ([^\n]+)", out.stderr):
        kind, desc = sm.groups()
        stream: dict = {"codec_type": kind.lower()}
        if kind == "Video":
            dm = re.search(r"(\d{2,5})x(\d{2,5})", desc)
            if dm:
                stream["width"], stream["height"] = int(dm.group(1)), int(dm.group(2))
            fm = re.search(r"([\d.]+) fps", desc)
            if fm:
                stream["r_frame_rate"] = f"{fm.group(1)}/1"
        else:
            sr = re.search(r"(\d+) Hz", desc)
            if sr:
                stream["sample_rate"] = sr.group(1)
        info["streams"].append(stream)
    return info


def media_duration(path: str | Path) -> float:
    info = probe(path)
    try:
        return float(info["format"].get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def video_dimensions(path: str | Path) -> tuple[int, int, float]:
    info = probe(path)
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            fps = 0.0
            fr = s.get("r_frame_rate") or "0/1"
            try:
                num, den = fr.split("/")
                fps = float(num) / float(den) if float(den) else 0.0
            except Exception:
                pass
            return int(s.get("width", 0)), int(s.get("height", 0)), fps
    return 0, 0, 0.0


def escape_filter_path(path: str | Path) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter graph argument."""
    p = str(path)
    return p.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def escape_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")
    return text.replace(",", "\\,").replace("[", "\\[").replace("]", "\\]").replace(";", "\\;")
