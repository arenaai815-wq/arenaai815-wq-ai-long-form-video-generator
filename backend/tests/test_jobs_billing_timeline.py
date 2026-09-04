"""Job progress math, credit estimates, timeline operations, caption formatting and security helpers."""
from __future__ import annotations

import time
import uuid

import pytest

from app.core.security import (
    create_access_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.models.enums import TERMINAL_STATES, JobState
from app.services.billing_service import estimate_pipeline_cost
from app.services.caption_service import to_srt, to_vtt, wrap_lines
from app.services.job_service import overall_progress
from app.services.timeline_service import apply_operation
from app.storage.local import sign_local_url, verify_local_signature

PIPELINE = [JobState.PROCESSING, JobState.GENERATING_SCRIPT, JobState.GENERATING_AUDIO, JobState.GENERATING_VISUALS, JobState.RENDERING]


def test_job_states_and_terminal_set():
    assert {s.value for s in JobState} >= {"QUEUED", "PROCESSING", "GENERATING_SCRIPT", "GENERATING_AUDIO", "GENERATING_VISUALS", "RENDERING", "COMPLETED", "FAILED", "CANCELLED"}
    assert TERMINAL_STATES == {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
    assert JobState.COMPLETED.is_terminal and not JobState.RENDERING.is_terminal


def test_overall_progress_is_monotonic_across_stages():
    last = 0.0
    for stage in PIPELINE:
        for frac in (0.0, 0.5, 1.0):
            p = overall_progress(stage, frac, PIPELINE)
            assert p >= last
            last = p
    assert 2 <= overall_progress(PIPELINE[0], 0.0, PIPELINE) < 10
    assert overall_progress(PIPELINE[-1], 1.0, PIPELINE) == pytest.approx(98)


def test_pipeline_cost_estimate_breakdown():
    est = estimate_pipeline_cost(duration_minutes=10, scene_count=60, ai_video_ratio=0.0)
    assert set(est) == {"research", "script", "voiceover", "images", "render"}
    assert est["research"] == 5 and est["script"] == 20 and est["images"] == 240 and est["render"] == 60
    with_video = estimate_pipeline_cost(duration_minutes=10, scene_count=60, ai_video_ratio=0.5)
    assert with_video["video_clips"] == 30 * 25 and with_video["images"] == 120
    only_render = estimate_pipeline_cost(duration_minutes=1, scene_count=5, stages=["render"])
    assert list(only_render) == ["render"]


def _doc():
    return {
        "version": 1,
        "tracks": [
            {"id": "t-video", "kind": "video", "clips": [
                {"id": "c1", "start": 0.0, "duration": 10.0, "trim_start": 0.0, "volume": 1.0, "transition_in": {"type": "fade", "duration": 0.6}},
                {"id": "c2", "start": 10.0, "duration": 8.0, "trim_start": 0.0, "volume": 1.0},
            ]},
            {"id": "t-music", "kind": "music", "clips": [{"id": "m1", "start": 0.0, "duration": 18.0, "volume": 0.12}]},
        ],
    }


def test_timeline_ops_trim_split_volume_fade_move_delete_transition_effect():
    doc = apply_operation(_doc(), "trim_clip", {"clip_id": "c1", "trim_start": 2.0})
    c1 = doc["tracks"][0]["clips"][0]
    assert c1["trim_start"] == 2.0 and c1["duration"] == 8.0

    doc = apply_operation(doc, "split_clip", {"clip_id": "c2", "at": 13.0})
    clips = doc["tracks"][0]["clips"]
    assert [c["id"].startswith("c2") for c in clips[1:]] == [True, True]
    assert clips[1]["duration"] == 3.0 and clips[2]["start"] == 13.0 and clips[2]["duration"] == 5.0 and clips[2]["trim_start"] == 3.0

    doc = apply_operation(doc, "set_volume", {"clip_id": "m1", "volume": 9.0})
    assert doc["tracks"][1]["clips"][0]["volume"] == 3.0  # clamped
    doc = apply_operation(doc, "set_fade", {"clip_id": "m1", "fade_in": 1.5, "fade_out": -1})
    assert doc["tracks"][1]["clips"][0]["fade_in"] == 1.5 and doc["tracks"][1]["clips"][0]["fade_out"] == 0.0
    doc = apply_operation(doc, "move_clip", {"clip_id": "m1", "start": -4})
    assert doc["tracks"][1]["clips"][0]["start"] == 0.0
    doc = apply_operation(doc, "set_transition", {"clip_id": "c1", "type": "wipeleft", "duration": 1.0})
    assert doc["tracks"][0]["clips"][0]["transition_in"] == {"type": "wipeleft", "duration": 1.0}
    doc = apply_operation(doc, "set_effect", {"clip_id": "c1", "type": "zoom_in", "intensity": 0.3})
    assert doc["tracks"][0]["clips"][0]["effect"] == {"type": "zoom_in", "intensity": 0.3}
    doc = apply_operation(doc, "delete_clip", {"clip_id": "m1"})
    assert doc["tracks"][1]["clips"] == []
    with pytest.raises(ValueError):
        apply_operation(doc, "set_volume", {"clip_id": "nope", "volume": 1})


def test_caption_formats():
    cues = [{"index": 1, "start": 0.15, "end": 2.5, "text": "Picture this. It is a quiet morning in the desert."}, {"index": 2, "start": 2.5, "end": 5.0, "text": "Nobody suspects what comes next."}]
    srt = to_srt(cues)
    assert srt.startswith("1\n00:00:00,150 --> 00:00:02,500\n")
    assert "\n\n2\n00:00:02,500 --> 00:00:05,000\n" in srt
    vtt = to_vtt(cues)
    assert vtt.startswith("WEBVTT\n") and "00:00:00.150 --> 00:00:02.500" in vtt
    lines = wrap_lines("one two three four five six seven", max_chars=20, max_lines=2)
    assert lines == ["one two three four", "five six seven"]  # greedy wrap within the limit
    overflow = wrap_lines("one two three four five six seven eight nine ten eleven twelve", max_chars=20, max_lines=2)
    assert len(overflow) == 2 and " ".join(overflow).split() == "one two three four five six seven eight nine ten eleven twelve".split()  # never drops words


def test_password_hashing_and_tokens():
    h = hash_password("Password123!")
    assert h != "Password123!" and verify_password("Password123!", h) and not verify_password("nope", h)
    uid, sid = uuid.uuid4(), uuid.uuid4()
    tok = create_access_token(uid, sid)
    payload = decode_token(tok, "access")
    assert payload["sub"] == str(uid) and payload["sid"] == str(sid)
    with pytest.raises(ValueError, match="wrong token type"):
        decode_token(tok, "refresh")  # an access token cannot be used as a refresh token
    with pytest.raises(ValueError, match="invalid token"):
        decode_token(tok[:-4] + "abcd", "access")  # tampered signature
    key, prefix, digest = generate_api_key()
    assert key.startswith(prefix) and digest == hash_api_key(key) and len(digest) == 64


def test_local_storage_signatures_expire_and_bind_to_key():
    exp = int(time.time()) + 60
    sig = sign_local_url("users/u/projects/p/renders/final.mp4", exp)
    assert verify_local_signature("users/u/projects/p/renders/final.mp4", exp, sig)
    assert not verify_local_signature("users/u/projects/p/renders/other.mp4", exp, sig)
    assert not verify_local_signature("users/u/projects/p/renders/final.mp4", exp - 120, sign_local_url("users/u/projects/p/renders/final.mp4", exp - 120))


def test_caption_font_scale_uses_short_side_and_narrows_lines():
    from app.services.caption_service import chars_per_line_for, font_scale

    assert font_scale(1920, 1080) == pytest.approx(1.0)
    assert font_scale(3840, 2160) == pytest.approx(2.0)
    assert font_scale(1080, 1920) == pytest.approx(1.0)  # portrait scales by width, not height
    assert font_scale(1080, 1080) == pytest.approx(1.0)
    assert chars_per_line_for(1920, 1080, 42) == 42
    assert chars_per_line_for(1080, 1920, 42) == 16  # clamped floor for 9:16
    assert chars_per_line_for(1080, 1080, 42) == 24
