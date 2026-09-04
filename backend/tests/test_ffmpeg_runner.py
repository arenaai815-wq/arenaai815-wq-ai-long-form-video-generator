"""The ffmpeg wrapper: progress parsing, cooperative cancellation and error propagation."""
from __future__ import annotations

import os
import shutil
import threading
import time

import pytest

from app.utils import ffmpeg as ff

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") or ff.ffmpeg_path()), reason="ffmpeg not available")


def _testsrc(seconds: float, out: str, size: str = "320x240") -> list[str]:
    return ["-f", "lavfi", "-i", f"testsrc=size={size}:rate=30", "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", out]


def test_progress_is_reported_and_reaches_one(tmp_path):
    out = tmp_path / "a.mp4"
    samples: list[float] = []
    ff.run_ffmpeg(_testsrc(3, str(out)), timeout=120, on_progress=samples.append, total_duration=3.0)
    assert out.exists() and out.stat().st_size > 1000
    assert samples and samples[-1] == pytest.approx(1.0, abs=0.05)
    assert samples == sorted(samples)


def test_should_stop_kills_encoder_quickly_and_raises(tmp_path):
    out = tmp_path / "b.mp4"
    flag = {"stop": False, "at": 0.0}

    def trip():
        time.sleep(1.5)
        flag["at"] = time.monotonic()
        flag["stop"] = True

    threading.Thread(target=trip, daemon=True).start()
    with pytest.raises(ff.FFmpegCancelled):
        ff.run_ffmpeg(_testsrc(120, str(out), size="1280x720"), timeout=300, should_stop=lambda: flag["stop"], poll_interval=0.25)
    assert time.monotonic() - flag["at"] < 3.0  # terminated within a couple of poll intervals
    time.sleep(0.3)
    # no orphaned encoder for this output file
    assert str(out) not in os.popen("ps -eo args").read()


def test_bad_input_raises_ffmpeg_error(tmp_path):
    with pytest.raises(ff.FFmpegError):
        ff.run_ffmpeg(["-i", str(tmp_path / "missing.mp4"), str(tmp_path / "c.mp4")], timeout=60)


def test_plain_run_without_progress(tmp_path):
    out = tmp_path / "d.mp4"
    ff.run_ffmpeg(_testsrc(0.5, str(out), size="160x120"), timeout=60)
    assert out.exists()
