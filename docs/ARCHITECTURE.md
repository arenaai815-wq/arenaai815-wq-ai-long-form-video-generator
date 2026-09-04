# Architecture notes

Companion to the top-level [README](../README.md). This document explains *why* the system is shaped the way it is and how a request travels through it.

## 1. Request → job → media

```
POST /projects/{id}/generate
 ├─ deps: authenticate (JWT / API key) → load project → assert ownership → rate limit
 ├─ billing: estimate credits for requested stages → reserve/charge (transactional)
 ├─ jobs:    upsert GenerationJob(idempotency_key) state=QUEUED
 ├─ queue:   celery.send_task("workers.tasks.generation.run_pipeline", queue="generation")
 └─ 202 {job}

worker (generation queue)
 ├─ run_job(): load job, guard terminal/idempotent replay, JobContext.start()
 ├─ stage loop: research → script → scenes → voiceover → visuals → captions
 │     each stage: ctx.set_state(...) → service call → provider call(s) → storage.put()
 │                 → DB rows → ctx.progress()/publish(ProgressEvent) → check_cancelled()
 ├─ render requested? create RenderJob(pipeline_job_id) → queue "render" → raise Handoff
 └─ else ctx.complete(result)

worker (render queue)
 ├─ resolve every asset on the main thread (download from object storage into the work dir)
 ├─ Compositor.render(): build filter graph, spawn ffmpeg, parse -progress, mirror to parent job
 ├─ upload MP4 + thumbnail → MediaAsset(kind=render) → RenderJob.output_*
 └─ complete render job → complete parent pipeline job → project.status = completed
```

## 2. Why two job tables

`generation_jobs` (LLM/TTS/image/video work: many small steps, retry-friendly) and `render_jobs` (one long FFmpeg process with output metadata) have different columns and lifetimes, but share the state machine, progress/ETA logic and SSE publishing through `JobContext`. The `/jobs` API merges both so the UI sees a single list.

## 3. Realtime

Workers publish `ProgressEvent` JSON to Redis channels `events:user:{uid}`, `events:project:{pid}` and `events:job:{jid}`. The API's SSE endpoints subscribe with a dedicated Redis connection per client and forward messages; a periodic `: ping` comment keeps proxies from closing idle streams. No websockets are needed because traffic is strictly server → client; the client mutates through REST.

The frontend keeps a single user-level `EventSource` (`JobToasts`) that invalidates TanStack Query caches on events, so pages never poll; the job/export/editor pages open scoped streams for finer updates.

## 4. Provider abstraction

Each capability has an abstract base in `app/providers/base.py` returning provider-neutral dataclasses (`LLMResult`, `ImageResult`, `VideoResult`, `SpeechResult` with `word_timings`, `TranscriptResult`, `StockItem`). Adapters translate to vendor APIs through `providers/http.py` (shared retry/backoff, timeout, error mapping to `ProviderError`). The registry instantiates adapters lazily from env and exposes `ProviderInfo` for `GET /providers`.

Mock adapters are first-class: deterministic, keyless, produce real files (PNG images with composition, WAV speech-like audio with word timings, MP4 clips) so rendering, captions and billing paths are exercised identically in development, CI and demos.

## 5. Timeline document

The editor works on a JSON document (`shared/schemas/timeline.json`): `tracks[] { kind: video|image|audio|voiceover|music|sfx|captions|text, clips[] { asset_id, start, duration, in, out, volume, fade_in, fade_out, effect, transition_in, ... } }`. It is derived from scenes (`/timeline/sync`) but user edits are preserved by clip id. Saves are optimistic (`base_version`) and small edits can be applied server-side (`/timeline/ops`) so the same op set backs undo/redo in the browser and automation via the API. The compositor consumes exactly this document, so what the editor shows is what FFmpeg renders.

## 6. Scaling knobs

| Concern | Knob |
|---|---|
| API throughput | replicas × `WEB_CONCURRENCY` (stateless; sessions in Postgres, rate limits in Redis) |
| AI throughput | `worker-generation` replicas × `WORKER_CONCURRENCY` (I/O bound); per-provider concurrency inside services (`asyncio.Semaphore`) |
| Render throughput | `worker-render` replicas (1 render per process, `RENDER_THREADS` for ffmpeg); plan `concurrent_renders` limits per user |
| Queue isolation | separate `generation` / `render` / `maintenance` queues — a render backlog never delays scripts |
| Storage | object storage + CDN (`STORAGE_PUBLIC_BASE_URL`); Postgres holds only metadata |
| Cost control | credit model per stage, plan limits (resolution, minutes, storage), idempotency keys |

## 7. Failure handling matrix

| Failure | Behaviour |
|---|---|
| Provider 5xx / timeout | retried inside the adapter (`PROVIDER_MAX_RETRIES`), then `ProviderError` → job retry with backoff (`max_attempts`), then `FAILED` + refund of unused credits |
| Worker dies mid-job | heartbeat expires → maintenance task marks job `FAILED` (`worker lost`), user can `retry` |
| Soft time limit | `SoftTimeLimitExceeded` → clean `FAILED`, temp dir removed |
| User cancels | Redis flag → checked between steps / ffmpeg killed → `CANCELLED` |
| Duplicate submission | same `idempotency_key` → existing job returned (`202`) |
| Stale editor save | `409 conflict` with current version; client rebases |
