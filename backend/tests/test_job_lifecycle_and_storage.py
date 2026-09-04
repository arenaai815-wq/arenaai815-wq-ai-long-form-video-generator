"""JobContext lifecycle logging, storage ObjectNotFound, render asset preflight and
PipelineRequest validation - all hermetic (no DB server, no Redis, no ffmpeg)."""
from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.enums import JobState
from app.models.job import GenerationJob, RenderJob
from app.services import job_service
from app.services.job_service import JobCancelled, JobContext


class _FakeSession:
    """Just enough of a SQLAlchemy Session for JobContext: commits are counted, never fail."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None: ...


@pytest.fixture
def ctx(monkeypatch):
    published: list[dict] = []
    monkeypatch.setattr(job_service, "publish_event", published.append)
    monkeypatch.setattr(job_service, "is_cancel_requested", lambda _id: False)
    job = GenerationJob(id=uuid.uuid4(), project_id=uuid.uuid4(), user_id=uuid.uuid4(), state=JobState.QUEUED, progress=0, attempt=0, max_attempts=3, logs=[], params={})
    from app.models.enums import JobType

    job.job_type = JobType.FULL_PIPELINE
    c = JobContext(_FakeSession(), job, worker_id="test-worker")
    c.published = published  # type: ignore[attr-defined]
    return c


def _messages(ctx: JobContext) -> list[str]:
    return [entry["message"] for entry in ctx.job.logs]


def test_lifecycle_writes_a_readable_log_trail(ctx):
    ctx.start()
    ctx.stage_progress(JobState.GENERATING_SCRIPT, 0.1, "Generating script... section 1/5")
    ctx.stage_progress(JobState.GENERATING_SCRIPT, 0.6, "Generating script... section 3/5")
    ctx.stage_progress(JobState.GENERATING_SCRIPT, 1.0, "Script complete")
    ctx.log("script: 900 words", stage="x")
    ctx.set_state(JobState.UPLOADING, "Uploading video...", progress=93)
    ctx.complete({"ok": True}, message="Video ready")

    msgs = _messages(ctx)
    assert msgs[0] == "attempt 1 started on worker test-worker"
    assert "Generating script started" in msgs
    # milestone entries at 50% and 100% (25% was skipped because the first tick jumped to 10% -> milestone 0)
    assert any(m.startswith("Generating script 50%") for m in msgs)
    assert any(m.startswith("Generating script 100%") for m in msgs)
    assert "script: 900 words" in msgs
    assert any(m.startswith("Uploading: Uploading video...") for m in msgs)
    assert msgs[-1] == "completed: Video ready"
    assert all("elapsed_s" in e and "ts" in e and "level" in e for e in ctx.job.logs)
    assert ctx.job.state == JobState.COMPLETED and ctx.job.progress == 100
    assert ctx.published[-1]["state"] == "COMPLETED"


def test_fail_and_cancel_are_logged_with_levels(ctx):
    ctx.start()
    ctx.fail("provider exploded", retrying=True)
    assert ctx.job.state == JobState.QUEUED
    assert ctx.job.logs[-1]["level"] == "error" and "will retry" in ctx.job.logs[-1]["message"]
    ctx.fail("provider exploded again")
    assert ctx.job.state == JobState.FAILED and ctx.job.error == "provider exploded again"
    assert ctx.job.logs[-1]["message"].startswith("failed: ")

    ctx.job.state = JobState.PROCESSING
    ctx.cancelled()
    assert ctx.job.state == JobState.CANCELLED
    assert ctx.job.logs[-1] == {**ctx.job.logs[-1], "level": "warning", "message": "cancelled by user"}


def test_log_is_capped_at_200_entries(ctx):
    for i in range(250):
        ctx.log(f"line {i}")
    assert len(ctx.job.logs) == 200 and ctx.job.logs[0]["message"] == "line 50"


def test_cancel_predicate_only_consults_redis_flag(ctx, monkeypatch):
    calls: list[str] = []

    def fake(job_id: str) -> bool:
        calls.append(job_id)
        return True

    monkeypatch.setattr(job_service, "is_cancel_requested", fake)
    pred = ctx.cancel_predicate()
    assert pred() is True and calls == [str(ctx.job.id)]
    with pytest.raises(JobCancelled):
        ctx.check_cancelled()


# ----------------------------------------------------------------------- storage


def test_local_storage_download_missing_key_raises_object_not_found(tmp_path, monkeypatch):
    from app.storage import ObjectNotFound
    from app.storage.local import LocalStorage

    st = LocalStorage.__new__(LocalStorage)
    monkeypatch.setattr(st, "_path", lambda key: tmp_path / key, raising=False)
    (tmp_path / "users").mkdir()
    (tmp_path / "users" / "a.png").write_bytes(b"x")
    assert st.download_to("users/a.png", tmp_path / "out.png").read_bytes() == b"x"
    with pytest.raises(ObjectNotFound) as ei:
        st.download_to("users/gone.png", tmp_path / "out2.png")
    assert ei.value.key == "users/gone.png"
    assert isinstance(ei.value, FileNotFoundError)


def test_render_preflight_names_missing_clips(ctx, tmp_path):
    from workers.rendering.compositor import AssetLocator
    from workers.tasks.render import MissingAssetError, _preflight_assets

    from app.storage import ObjectNotFound

    ok, gone, unknown = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())

    def resolve(asset_id: str, kind: str | None) -> Path | None:
        if asset_id == ok:
            return tmp_path / "ok.png"
        if asset_id == gone:
            raise ObjectNotFound("users/u/projects/p/ai-images/gone.png")
        return None

    doc = {
        "tracks": [
            {"kind": "video", "clips": [{"id": "c1", "label": "Intro", "asset_id": ok}, {"id": "c2", "label": "Conclusion", "asset_id": gone}, {"id": "c3", "label": "Card"}]},
            {"kind": "voiceover", "clips": [{"id": "v1", "label": "Scene 2 VO", "asset_id": unknown, "asset_kind": "voiceover"}]},
        ]
    }
    with pytest.raises(MissingAssetError) as ei:
        _preflight_assets(ctx, doc, AssetLocator(resolve=resolve))
    msg = str(ei.value)
    assert "2 media asset(s)" in msg and "video clip 'Conclusion'" in msg and "voiceover clip 'Scene 2 VO'" in msg
    assert "not in database" in msg and "gone.png" in msg
    assert ctx.job.logs[-1]["level"] == "warning" and "2 MISSING" in ctx.job.logs[-1]["message"]
    assert isinstance(ei.value, ValueError)  # -> NON_RETRYABLE in workers.tasks.base

    # all present -> no exception, info log
    _preflight_assets(ctx, {"tracks": [{"kind": "video", "clips": [{"id": "c1", "asset_id": ok}]}]}, AssetLocator(resolve=resolve))
    assert ctx.job.logs[-1]["message"] == "assets: 1 referenced, 1 available"


# ----------------------------------------------------------------------- schemas


def test_pipeline_request_orders_stages_and_validates_options():
    import pydantic

    from app.schemas.job import PipelineRequest

    assert PipelineRequest(stages=["render", "script", "research"]).stages == ["research", "script", "render"]
    assert PipelineRequest(options={"voiceover": {"speed": 1.1}}).options == {"voiceover": {"speed": 1.1}}
    with pytest.raises(pydantic.ValidationError, match="unknown stage"):
        PipelineRequest(stages=["research", "bogus"])
    with pytest.raises(pydantic.ValidationError, match="options for unknown stage"):
        PipelineRequest(options={"render": {"fps": 60}})


def test_render_job_is_a_job_for_event_building():
    job = RenderJob(id=uuid.uuid4(), project_id=uuid.uuid4(), user_id=uuid.uuid4(), state=JobState.RENDERING, progress=40, stage="Rendering video", message="clip 4/10", width=1920, height=1080, fps=30, logs=[])
    ev = job_service.event_for(job)
    assert ev["job_type"] == "render" and ev["state"] == "RENDERING" and ev["progress"] == 40
    assert SimpleNamespace(**ev).message == "clip 4/10"
