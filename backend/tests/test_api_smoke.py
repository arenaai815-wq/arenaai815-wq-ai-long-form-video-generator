"""Live API smoke test (needs a running stack: API + worker + Postgres + Redis).

    E2E_BASE_URL=http://localhost:8000 pytest -q tests/test_api_smoke.py

Creates a throw-away user, runs the full pipeline for a 1-minute project with mock providers
and asserts the MP4 export exists. Skipped when E2E_BASE_URL is unset.
"""
from __future__ import annotations

import json
import time

import httpx
import pytest


@pytest.fixture(scope="module")
def client(e2e_base_url: str) -> httpx.Client:
    c = httpx.Client(base_url=f"{e2e_base_url}/api/v1", timeout=60)
    r = c.post("/auth/signup", json={"email": f"smoke{int(time.time())}@example.com", "password": "Password123!", "full_name": "Smoke Test"})
    assert r.status_code == 201, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


def test_health(client: httpx.Client):
    assert client.get("/health").json()["status"] == "ok"
    workers = client.get("/health/workers").json()
    assert any(w["healthy"] for w in workers), "no healthy worker online"


def test_full_pipeline_produces_mp4(client: httpx.Client):
    r = client.post("/projects", json={"title": "Smoke", "topic": "The history of coffee", "tone": "documentary", "target_duration_minutes": 1, "resolution": "720p"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    est = client.get(f"/projects/{pid}/estimate").json()
    assert est["sufficient"] and est["credits"] > 0

    job = client.post(f"/projects/{pid}/generate", json={"idempotency_key": f"smoke-{pid}"}).json()
    replay = client.post(f"/projects/{pid}/generate", json={"idempotency_key": f"smoke-{pid}"}).json()
    assert replay["id"] == job["id"], "idempotency key must return the same job"

    states: list[str] = []
    with client.stream("GET", f"/jobs/{job['id']}/events", timeout=900) as s:
        for line in s.iter_lines():
            if line.startswith("data:"):
                ev = json.loads(line[5:])
                if not states or states[-1] != ev["state"]:
                    states.append(ev["state"])
            elif line.startswith("event: done"):
                break
    assert states[-1] == "COMPLETED", states
    # Mock stages can finish between two SSE samples, so only the slow ones are guaranteed to be observed.
    assert "RENDERING" in states, states
    logs = client.get(f"/jobs/{job['id']}/logs").json()["logs"]
    assert any("Generating voiceover" in entry["message"] for entry in logs), "voiceover stage should be in the job log"

    export = client.get(f"/projects/{pid}/export")
    assert export.status_code == 200, export.text
    info = export.json()
    assert info["duration_seconds"] > 30 and info["width"] == 1280 and info["size_bytes"] > 100_000
    mp4 = httpx.get(info["url"] if info["url"].startswith("http") else f"{client.base_url.scheme}://{client.base_url.host}:{client.base_url.port}{info['url']}", timeout=120)
    assert mp4.status_code == 200 and mp4.headers["content-type"].startswith("video/")

    project = client.get(f"/projects/{pid}").json()
    assert project["status"] == "completed" and all(project["pipeline"].values())
    assert client.get(f"/projects/{pid}/captions/export.srt").text.startswith("1\n")
    summary = client.get("/usage/summary").json()
    assert summary["credits_used"] > 0 and summary["videos_completed"] >= 1
