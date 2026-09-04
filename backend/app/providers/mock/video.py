"""Mock video provider - produces a real H.264 MP4 clip with motion, built via FFmpeg."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.providers.base import UsageMetrics, VideoProvider, VideoResult
from app.providers.mock.image import render_placeholder
from app.utils.ffmpeg import run_ffmpeg


class MockVideoProvider(VideoProvider):
    name = "mock"
    display_name = "Mock Video Generator (development)"
    is_mock = True
    model = "mock-video-v1"

    def capabilities(self) -> dict[str, Any]:
        return {"max_duration": 20, "image_to_video": True, "max_width": 1920, "max_height": 1080}

    def generate_video(
        self,
        prompt: str,
        *,
        width: int = 1280,
        height: int = 720,
        duration_seconds: float = 5.0,
        fps: int = 24,
        image: bytes | None = None,
        style: str | None = None,
        model: str | None = None,
    ) -> VideoResult:
        done = self._timer()
        duration_seconds = max(1.0, min(20.0, float(duration_seconds)))
        with tempfile.TemporaryDirectory(prefix="mockvideo_") as tmp:
            tmpd = Path(tmp)
            src = tmpd / "frame.png"
            if image:
                src.write_bytes(image)
            else:
                # Render at 1.3x so the zoom/pan has room to move without upscaling artifacts
                src.write_bytes(render_placeholder(prompt, int(width * 1.3), int(height * 1.3), label=prompt.split(",")[0][:80]))
            out = tmpd / "clip.mp4"
            frames = int(duration_seconds * fps)
            zoompan = (
                f"scale=8000:-1,zoompan=z='min(zoom+0.0008,1.25)':d={frames}"
                f":x='iw/2-(iw/zoom/2)+sin(on/40)*20':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
            )
            run_ffmpeg(
                [
                    "-loop", "1", "-framerate", str(fps), "-i", str(src),
                    "-vf", f"{zoompan},format=yuv420p",
                    "-t", f"{duration_seconds:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-movflags", "+faststart", "-an", str(out),
                ],
                timeout=300,
            )
            data = out.read_bytes()
        return VideoResult(
            data=data,
            content_type="video/mp4",
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            fps=float(fps),
            usage=UsageMetrics(provider=self.name, model=self.model, seconds=duration_seconds, latency_ms=done()),
        )
