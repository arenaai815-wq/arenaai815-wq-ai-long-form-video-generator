# LongForm AI — AI long-form video generation platform

Turn a topic into a fully produced long-form video (5–60+ minutes): **research → script → storyboard → voiceover → visuals → captions → FFmpeg render → MP4**. Built as a scalable AI video production pipeline — async workers, job queues, object storage, provider abstraction — not a toy editor.

```
topic ──► AI research ──► AI script ──► scenes/storyboard ──► voiceover (TTS)
      ──► visuals (AI image / AI video / stock / uploads) ──► captions (SRT/VTT)
      ──► timeline (multi-track) ──► FFmpeg render (Ken Burns, xfade, ducking, burn-in, watermark) ──► MP4
```

| Layer | Stack |
|---|---|
| Frontend | Next.js 14 (App Router) · React · TypeScript · Tailwind · TanStack Query · Zustand |
| Backend API | Python 3.11+ · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 |
| Workers | Celery (queues `generation`, `render`, `maintenance`) · Redis broker · FFmpeg |
| Data | PostgreSQL 16 · Redis 7 · S3-compatible object storage (AWS S3 / MinIO / R2) with signed URLs |
| Realtime | Server-Sent Events fed by Redis pub/sub (per user / project / job) |
| AI providers | Pluggable adapters: LLM, image, video, TTS, STT, stock media — with offline **mock** providers |

---

## Table of contents

1. [Quick start](#quick-start)
2. [Repository layout](#repository-layout)
3. [Architecture](#architecture)
4. [The generation pipeline](#the-generation-pipeline)
5. [Job system](#job-system)
6. [AI provider abstraction](#ai-provider-abstraction)
7. [Rendering](#rendering)
8. [Storage](#storage)
9. [Security](#security)
10. [Billing & usage](#billing--usage)
11. [API reference](#api-reference)
12. [Configuration](#configuration)
13. [Development](#development)
14. [Production deployment](#production-deployment)
15. [Extending](#extending)

---

## Quick start

### Option A — Docker (everything, including Postgres/Redis/MinIO)

```bash
cp .env.example .env
docker compose -f infrastructure/docker-compose.yml up --build
```

* App: <http://localhost:3000> · API docs: <http://localhost:8000/api/v1/docs> · MinIO console: <http://localhost:9001>
* Seeded admin: `admin@longform.local` / `admin12345` (run `docker compose -f infrastructure/docker-compose.yml run --rm migrate seed`)
* No API keys required — all AI capabilities default to deterministic **mock providers**, so the full pipeline (including a real rendered MP4) works offline. Add keys in `.env` to switch to real providers.

### Option B — local processes

Requirements: Python 3.11+, Node 20+, PostgreSQL and Redis (or `make infra` to run them in Docker), FFmpeg (auto-provided via `imageio-ffmpeg` if not on `PATH`; system FFmpeg with libass is recommended for production).

```bash
make infra          # optional: Postgres + Redis + MinIO in Docker
make bootstrap      # venv, deps, .env, migrations, seed
make dev            # API :8000 (reload) + Celery worker/beat + Next.js :3000
```

Or run the pieces yourself:

```bash
cd backend && export PYTHONPATH=..:.
alembic upgrade head && python -m scripts.seed
uvicorn app.main:app --reload --port 8000
celery -A workers.celery_app:celery_app worker -Q generation,render,maintenance -c 2 -B --loglevel INFO
cd ../frontend && npm install && npm run dev
```

### First video (UI)

1. Sign up → **New project** (title, topic, niche, audience, language, tone, duration, aspect ratio, resolution, visual style).
2. Click **Generate video** on the project page — or step through **Research → Script → Storyboard → Editor → Export** manually. Every step can be edited and regenerated individually.
3. Watch live progress (SSE) on the dashboard/jobs page; download the MP4, SRT and VTT from **Export**.

### First video (API)

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/signup -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"Password123!","full_name":"Me"}' | jq -r .access_token)
PID=$(curl -s localhost:8000/api/v1/projects -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"title":"The Silent History of the Sahara","topic":"How the Sahara turned from savanna to desert","tone":"documentary","target_duration_minutes":5,"resolution":"1080p"}' | jq -r .id)
curl -s localhost:8000/api/v1/projects/$PID/generate -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{}'
curl -N "localhost:8000/api/v1/jobs/projects/$PID/events?token=$TOKEN"     # live progress stream
curl -s localhost:8000/api/v1/projects/$PID/export -H "authorization: Bearer $TOKEN"   # signed MP4 URL when done
```

---

## Repository layout

```
frontend/          Next.js app (App Router). /api/* is proxied server-side to the backend.
backend/
  app/
    api/v1/        Route modules (auth, projects, research, scripts, scenes, voiceovers, captions,
                   timeline, render, jobs, media, usage, billing, providers, health)
    api/deps.py    Auth / ownership / rate-limit dependencies
    core/          config (pydantic-settings), security (argon2 + JWT), logging, errors, rate limiting
    db/            async + sync SQLAlchemy sessions, base model
    models/        User, Project, Research, Script, ScriptSection, Scene, MediaAsset, AudioAsset,
                   Voiceover, Timeline, Caption, RenderJob, GenerationJob, AIProvider, Plan,
                   Subscription, UsageRecord, CreditTransaction, Session, ApiKey (+ enums, indexes)
    schemas/       Pydantic request/response models (the API contract)
    services/      Domain logic: research, script, scene, visual, voiceover, caption, timeline,
                   media, billing, job lifecycle (JobContext), prompt templates
    providers/     Provider interfaces + registry + adapters (llm/, image/, video/, tts/, stt/,
                   stock/) and offline mock/ implementations
    storage/       Storage interface: local (signed paths) and S3 (presigned URLs)
    realtime/      Redis pub/sub → SSE event bus
    utils/         text/duration estimation, ffmpeg helpers, ids, slugs
  alembic/         Database migrations
  scripts/seed.py  Plans + admin user + system music library
workers/
  celery_app.py    Celery app, queues, beat schedule
  tasks/           generation.py (pipeline stages), render.py, maintenance.py, base.py (run_job)
  rendering/       compositor.py (FFmpeg graph builder), text_cards.py (intro/outro/overlays)
shared/            JSON schemas shared by both sides (job states, progress events, timeline document)
infrastructure/    docker-compose.yml (+ prod overlay), Dockerfiles, entrypoint, dev/bootstrap scripts
docs/              API docs & architecture notes
```

---

## Architecture

```
                  ┌──────────────────────────────┐
   browser ─────► │ Next.js (SSR + static)       │  /api/* rewrite (server-side) ──┐
                  └──────────────────────────────┘                                 ▼
                                                              ┌──────────────────────────────┐
                                                              │ FastAPI  (stateless, N pods) │
                                                              │  auth · REST · SSE · signing │
                                                              └───────┬──────────┬───────────┘
                                                                      │          │ publish progress
                       ┌──────────────┐   ┌──────────────┐            ▼          ▼
                       │ PostgreSQL   │◄──┤ Celery       │◄──── Redis (broker · pub/sub · rate limits · cancel flags)
                       │ (state only) │   │ workers      │
                       └──────────────┘   │ generation ×N│───► AI providers (LLM / image / video / TTS / STT / stock)
                                          │ render     ×N│───► FFmpeg
                                          │ beat       ×1│
                                          └──────┬───────┘
                                                 ▼
                                    S3-compatible object storage (all media, presigned URLs)
```

* **Web process never does heavy work.** Every AI call and every FFmpeg invocation runs in a Celery worker. HTTP handlers validate, charge credits, create a job row, enqueue and return `202`.
* **Postgres holds state, not bytes.** Media/renders live in object storage; the DB stores keys, metadata and signed-URL generation happens on read.
* **Realtime without polling.** Workers publish `ProgressEvent`s to Redis; the API fans them out as SSE (`/jobs/events`, `/jobs/projects/{id}/events`, `/jobs/{id}/events`). The frontend invalidates its query cache on events.
* **Horizontal scaling.** API pods are stateless (JWT + Redis). Generation workers are I/O bound (scale concurrency); render workers are CPU bound (one render per process, scale replicas). Queues are separate so a render backlog never blocks script generation.

---

## The generation pipeline

`POST /projects/{id}/generate` creates a `full_pipeline` GenerationJob that runs the requested stages in order (default: all), skipping stages whose output already exists (`skip_existing`). Each stage is also available as its own endpoint/job so users can regenerate any step.

| Stage | Job state | What happens |
|---|---|---|
| research | `PROCESSING` | LLM produces summary, key facts, statistics, sources, keywords organised into sections. User-editable (`PUT /research`). |
| script | `GENERATING_SCRIPT` | Outline (hook, intro, N chapters sized to duration, transitions, conclusion, CTA) → each section written with facts from research. Word count + narration estimate per section; versions kept; per-section regenerate/lock/reorder. |
| scenes | `PROCESSING` | Sections split into scenes (~9 s target): narration, visual description, suggested footage, image/video prompt, on-screen text, duration, transition, music mood. |
| voiceover | `GENERATING_AUDIO` | TTS per scene (parallel), word timings kept for captions; scene durations snap to audio. |
| visuals | `GENERATING_VISUALS` | Per scene: AI image / AI video clip / stock search / reuse, according to project settings. Assets are stored, deduplicated and reusable. |
| captions | `PROCESSING` | Cues built from TTS word timings (or STT alignment); SRT/VTT exports; style config. |
| render | `RENDERING` → `UPLOADING` | Timeline synced from scenes; render job on the `render` queue; MP4 uploaded, export ready. |

Credits are estimated up front (`POST /projects/{id}/estimate`) and charged per stage; failures refund the unused portion.

---

## Job system

Two job tables (`generation_jobs`, `render_jobs`) share one lifecycle implemented in `app/services/job_service.py` (`JobContext`) and `workers/tasks/base.py` (`run_job`):

* **States:** `QUEUED → PROCESSING → GENERATING_SCRIPT | GENERATING_AUDIO | GENERATING_VISUALS | RENDERING | UPLOADING → COMPLETED | FAILED | CANCELLED` (see `shared/schemas/job_states.json`).
* **Progress + ETA:** stage-weighted percent, message ("Generating voiceover... 7/10 scenes"), ETA from measured stage throughput. Published on every update.
* **Retries:** transient errors → Celery retry with backoff up to `max_attempts` (`attempt` tracked in DB); non-retryable errors (validation, provider refusal, missing media, no credits) fail fast with a human-readable `error`. `POST /jobs/{id}/retry` re-queues a failed or cancelled job: pipeline retries resume from the last completed stage, render retries reuse already-encoded scene clips.
* **Timeouts:** soft/hard Celery time limits per queue (`JOB_DEFAULT_TIMEOUT_SECONDS`, `RENDER_JOB_TIMEOUT_SECONDS`); soft limit produces a clean `FAILED` with error.
* **Cancellation:** `POST /jobs/{id}/cancel` sets a Redis flag; workers poll it between steps *and* inside long native steps — a running FFmpeg encode is terminated within ~1 s → `CANCELLED`. Render credits are only charged on completion, so a cancelled render costs nothing.
* **Idempotency:** `idempotency_key` on generation/render requests returns the existing job instead of creating a duplicate; task delivery is idempotent (terminal jobs are skipped).
* **Hand-off:** the pipeline job delegates to a render job and stays `RENDERING`; the render worker mirrors progress to the parent and completes/fails it.
* **Health:** workers heartbeat into Redis every 20 s (`GET /health/workers`), queue depths and 24 h stats at `GET /health/queues`; beat reaps stale jobs whose worker died and cleans temp dirs.
* **Logs:** every job keeps a persisted, structured trail (`GET /jobs/{id}/logs`): worker pickup, stage transitions and milestones, the provider/model each stage used, per-stage summaries (words, scenes, audio seconds, assets, encode size/time) and the final completion / failure / cancellation entry, plus `error` / `error_details` (type + traceback) for failures. Visible in the UI from the Jobs page and the Export page.

---

## AI provider abstraction

`backend/app/providers/base.py` defines one interface per capability; `registry.py` resolves the active implementation from env (`LLM_PROVIDER`, `IMAGE_PROVIDER`, `VIDEO_PROVIDER`, `TTS_PROVIDER`, `STT_PROVIDER`, `STOCK_PROVIDER`).

| Capability | Interface | Adapters |
|---|---|---|
| LLM | `LLMProvider.complete / complete_json` | `openai`, `openai_compatible` (any OpenAI-style gateway), `anthropic`, `mock` |
| Image | `ImageProvider.generate_image` | `openai`, `stability`, `replicate`, `mock` (renders styled composition + prompt) |
| Video | `VideoProvider.generate_clip` (async job polling) | `replicate`, `runway`, `mock` (`luma` slot reserved in config) |
| TTS | `TTSProvider.synthesize / list_voices` (word timings when supported) | `openai`, `elevenlabs`, `mock` (synthesised speech-like audio at the estimated pace) |
| STT | `STTProvider.transcribe` (word-level) | `openai_whisper`, `deepgram`, `mock` |
| Stock | `StockProvider.search / download` | `pexels`, `mock` (`pixabay` slot reserved in config) |

Common concerns live in `providers/http.py`: timeouts, retries with backoff, rate-limit handling, cost/usage reporting. Mock providers are deterministic (seeded by input) so tests and demos are reproducible. `GET /providers` reports what is active/configured (never keys).

---

## Rendering

`workers/rendering/compositor.py` builds a single FFmpeg filter graph from the timeline document (`shared/schemas/timeline.json`):

* per clip: scale/crop to the output frame, **Ken Burns / zoom / pan** (`zoompan`) or static, trim; video clips keep their own motion
* **transitions** between scenes with `xfade` (fade, dissolve, wipes, slides…) and matching `acrossfade`
* **audio mix:** voiceover track + music with **sidechain ducking**, SFX, per-clip volume and fade in/out, `loudnorm` (-16 LUFS) + limiter
* **captions** burned in via ASS (`subtitles` filter) with configurable font/size/colour/position/animation; or exported as SRT/VTT sidecars
* **text overlays / on-screen text**, **intro & outro** cards, **watermark** (text or image, position/opacity; forced on free plan)
* output: H.264 (`libx264`, CRF/preset configurable) + AAC, `+faststart` MP4; 16:9 / 9:16 / 1:1, 720p → 4K; previews render at ≤720p, ranges supported
* scene clips are encoded in parallel (`RENDER_MAX_PARALLEL_CLIPS`) into a per-job work dir with atomic `.part` → `.mp4` writes, then joined with transitions, mixed and finalised; a retry after a crash/cancel skips clips that already finished
* before encoding, every asset referenced by the timeline is resolved (downloaded from object storage on demand); a missing object fails the job immediately with the offending scene/clip named
* progress parsed from FFmpeg `-progress` and streamed to the job; cooperative cancellation terminates the encoder within ~1 s (never leaves orphaned `ffmpeg` processes)
* captions, text overlays and the watermark scale by the frame's short side so 9:16 / 1:1 output gets the same visual size as 16:9

---

## Storage

`app/storage/` exposes one interface (`put`, `get`, `delete`, `signed_url`, `presign_upload`, `size`).

* `s3`: any S3-compatible bucket; browser downloads/uploads use **presigned URLs** (bucket stays private). Large uploads go straight to the bucket (`/media/uploads/init` → PUT → `/media/uploads/complete`).
* `local`: files under `STORAGE_LOCAL_PATH`, served via HMAC-signed, expiring `/media/files/{key}` URLs (dev / single-node).
* Every asset row stores key, size, dimensions/duration, checksum, provenance (prompt/provider/source) and reusability; storage quotas are enforced per plan.

---

## Security

* Passwords hashed with **Argon2id**; JWT access tokens (30 min) + revocable refresh sessions (device list, revoke, logout-all on password change).
* **API keys** (`X-API-Key`, hashed at rest, prefix shown, scopes, revocation) for programmatic access.
* Every project/asset/job route enforces **ownership** through dependencies; admin-only routes for provider health.
* **Rate limiting** (Redis-backed, per user/IP; tighter on auth and generation), request IDs, structured error envelope `{error:{code,message,details}}`.
* Secrets only via environment; the frontend proxies `/api` server-side so browsers never see provider keys or backend hosts. Security headers set by Next.js; CORS restricted to `CORS_ORIGINS`.
* Signed, expiring media URLs; uploads validated by type/size; presigned PUTs scoped to a single key.

---

## Billing & usage

* Every billable action writes a `UsageRecord` (kind, quantity, unit, credits, provider, project) and a `CreditTransaction` (grant / charge / refund / purchase). Balance is computed transactionally.
* Default costs: research 5 · script 2/min · TTS 3 per 1k chars · image 4 · video clip 25 · render 6/min (all env-configurable).
* Plans (`free`, `creator`, `pro`, `studio`) define monthly credits, storage, max resolution, concurrent renders and watermark policy — enforced in the render route and uploads.
* **Stripe-ready:** `billing_service.py` implements checkout / portal / cancel / webhook handlers behind a provider flag. Without `STRIPE_SECRET_KEY` it runs in *sandbox* mode (plans and credit packs are applied immediately) so the flow is testable end-to-end.

---

## API reference

Interactive docs: `GET /api/v1/docs` (Swagger) · `GET /api/v1/redoc` · `GET /api/v1/openapi.json`. Full endpoint list: [`docs/API.md`](docs/API.md).

Auth: `Authorization: Bearer <access_token>` or `X-API-Key: <key>`. SSE endpoints also accept `?token=`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/signup` `login` `refresh` `logout` · `GET/PATCH /auth/me` · `POST /auth/me/password` · `GET/DELETE /auth/sessions` · `GET/POST/DELETE /auth/api-keys` |
| Projects | `GET/POST /projects` · `GET /projects/stats` · `GET/PATCH/DELETE /projects/{id}` · `POST …/restore` `duplicate` `estimate` `generate` · `GET …/jobs` `export` |
| Research | `GET/PUT /projects/{id}/research` · `POST …/research/generate` |
| Script | `GET/PATCH /projects/{id}/script` · `GET …/script/stats` `versions` · `POST …/versions/{v}/restore` `generate` `sections` `sections/reorder` `sections/{sid}/regenerate` `sections/{sid}/lock` · `PATCH/DELETE …/sections/{sid}` |
| Scenes | `GET/POST /projects/{id}/scenes` · `POST …/scenes/generate` `visuals/generate` `reorder` `{sid}/split` `{sid}/visual/from-asset` `{sid}/visual/from-stock` · `GET/PATCH/DELETE …/scenes/{sid}` · `DELETE …/{sid}/visual` |
| Voice | `GET /voices` · `POST /voices/preview` · `GET/POST /projects/{id}/voiceovers` `generate` · `GET/DELETE …/voiceovers/{vid}` |
| Captions | `GET/PUT /projects/{id}/captions` · `POST …/captions/generate` · `GET …/captions/export.srt` `export.vtt` |
| Timeline | `GET/PUT /projects/{id}/timeline` (optimistic `base_version`) · `POST …/timeline/ops` (`reorder_scenes`, `trim_clip`, `split_clip`, `set_volume`, `set_fade`, `move_clip`, `delete_clip`, `set_transition`, `set_effect`) · `POST …/timeline/sync` |
| Render | `POST /projects/{id}/render` (`preview`, `resolution`, `fps`, `burn_captions`, `include_watermark`, `range_start/end`, `idempotency_key`) · `GET …/renders` `renders/{rid}` |
| Jobs | `GET /jobs` (`state`, `project_id`, `active`) · `GET /jobs/{id}` `logs` · `POST /jobs/{id}/cancel` `retry` · SSE `GET /jobs/events` `/jobs/projects/{pid}/events` `/jobs/{id}/events` |
| Media | `GET /media` `storage` `audio` · `POST /media/upload` `uploads/init` `uploads/complete` · `GET/PATCH/DELETE /media/{id}` · `GET /media/stock/search` · `POST /media/stock/import` · `GET /media/files/{key}` (signed) |
| Usage & billing | `GET /usage/summary` `records` `credits` `projects` · `GET /billing/plans` `subscription` `portal` · `POST /billing/subscription/change` `subscription/cancel` `checkout` `credits/purchase` `webhooks/stripe` |
| System | `GET /providers` `/providers/{kind}/models` · `GET /health` `health/workers` `health/queues` |

---

## Configuration

All settings are environment variables (see [`.env.example`](.env.example) for the annotated list). Key groups:

| Group | Variables |
|---|---|
| Core | `SECRET_KEY` `ENVIRONMENT` `FRONTEND_URL` `CORS_ORIGINS` `DATABASE_URL` `REDIS_URL` |
| Providers | `LLM_PROVIDER` `IMAGE_PROVIDER` `VIDEO_PROVIDER` `TTS_PROVIDER` `STT_PROVIDER` `STOCK_PROVIDER` + `OPENAI_API_KEY` `ANTHROPIC_API_KEY` `ELEVENLABS_API_KEY` `STABILITY_API_KEY` `REPLICATE_API_TOKEN` `RUNWAY_API_KEY` `DEEPGRAM_API_KEY` `PEXELS_API_KEY` … |
| Storage | `STORAGE_BACKEND` (`local`/`s3`) `S3_ENDPOINT_URL` `S3_BUCKET` `S3_ACCESS_KEY_ID` `S3_SECRET_ACCESS_KEY` `SIGNED_URL_EXPIRE_SECONDS` |
| Rendering | `FFMPEG_BINARY` `RENDER_PRESET` `RENDER_CRF` `RENDER_THREADS` `FONT_PATH` `WATERMARK_TEXT` `MAX_VIDEO_DURATION_MINUTES` |
| Jobs | `JOB_DEFAULT_TIMEOUT_SECONDS` `RENDER_JOB_TIMEOUT_SECONDS` `JOB_MAX_RETRIES` `WORKER_HEARTBEAT_TTL_SECONDS` |
| Billing | `FREE_PLAN_CREDITS` `CREDIT_COST_*` `STRIPE_SECRET_KEY` `STRIPE_WEBHOOK_SECRET` `STRIPE_PRICE_*` |
| Frontend | `API_INTERNAL_URL` (server-side only; see `frontend/.env.example`) |

---

## Development

```bash
make help            # all targets
make lint            # ruff + tsc + eslint
make test            # pytest (backend)
make migration m="add scene tags"   # alembic autogenerate
make build           # production build of the frontend
```

* Backend hot-reload: `uvicorn app.main:app --reload`; workers must be restarted to pick up task changes.
* Mock providers are the default; set `LLM_PROVIDER=openai` + `OPENAI_API_KEY=…` (etc.) to exercise real adapters. Any OpenAI-compatible gateway works via `LLM_PROVIDER=openai_compatible` + `OPENAI_BASE_URL`.
* Rendering locally without a system FFmpeg works through the `imageio-ffmpeg` binary (no `drawtext`; captions use libass/ASS and text cards are rasterised with Pillow, so nothing depends on `drawtext`).
* Generated data lives in `data/` (git-ignored). Frontend dev server proxies `/api` to `API_INTERNAL_URL`.


### Continuous integration

A ready-to-use GitHub Actions workflow lives at [`infrastructure/ci/github-actions-ci.yml`](infrastructure/ci/github-actions-ci.yml) (ruff + pytest, tsc + eslint + `next build`, and a live end-to-end job that boots Postgres/Redis, the API and a worker, then runs signup → full pipeline → MP4 with mock providers and real FFmpeg). Enable it with:

```bash
mkdir -p .github/workflows && cp infrastructure/ci/github-actions-ci.yml .github/workflows/ci.yml
```

(It is kept outside `.github/` because automated pushes from apps without the `workflows` permission are rejected by GitHub.)

---

## Production deployment

**Reference topology:** managed PostgreSQL + Redis, an S3 bucket (or MinIO/R2), N stateless API containers, generation workers, render workers with more CPU, exactly one beat, the Next.js container behind a TLS-terminating reverse proxy.

1. **Images** — build once, deploy anywhere:
   ```bash
   docker build -f infrastructure/docker/backend.Dockerfile  --target api    -t longform-api .
   docker build -f infrastructure/docker/backend.Dockerfile  --target worker -t longform-worker .
   docker build -f infrastructure/docker/frontend.Dockerfile                  -t longform-web .
   ```
   The backend image ships FFmpeg (libx264/libass) and fonts; the entrypoint accepts `api | worker | beat | migrate | seed`.
2. **Configure** — production `.env`: strong `SECRET_KEY`, `ENVIRONMENT=production`, `STORAGE_BACKEND=s3` + bucket credentials, real provider keys, `FRONTEND_URL`/`CORS_ORIGINS`, Stripe keys if billing is live.
3. **Migrate** — `docker run --env-file .env longform-api migrate` (or the `migrate` compose service / a K8s Job). Migrations are forward-only Alembic revisions.
4. **Run** — single host: `docker compose -f infrastructure/docker-compose.yml -f infrastructure/docker-compose.prod.yml up -d` (external Postgres/Redis/S3; scale with `--scale worker-render=N`). Kubernetes/ECS: one Deployment per image+command (`api`, `worker` with `WORKER_QUEUES=generation,maintenance`, `worker` with `WORKER_QUEUES=render`, `beat` replicas=1, `web`), HPA on CPU for workers, readiness on `/api/v1/health`.
5. **Frontend** — set `API_INTERNAL_URL=http://api:8000` (cluster-internal). Only the web container needs public ingress; put TLS/HTTP2 termination and a 30-minute proxy read timeout in front (SSE streams and large downloads).
6. **Observability** — structured JSON logs with request/job IDs, `/health/workers` + `/health/queues` for dashboards/alerts (workers offline, failed_24h, queue depth), Celery events compatible with Flower.
7. **Operations** — `WORKER_MAX_TASKS_PER_CHILD` recycles render processes; `RENDER_WORK_DIR` should be fast local disk (emptyDir/NVMe); object storage lifecycle rules can expire preview renders; rotate `SECRET_KEY` by deploying with both old/new (sessions are DB-backed and will simply require re-login).

---

## Extending

* **New AI provider:** implement the interface in `app/providers/<kind>/`, register it in `providers/registry.py`, add its env vars to `core/config.py` and `.env.example`. It appears automatically in `GET /providers` and the Settings page.
* **New pipeline stage:** add a stage function in `workers/tasks/generation.py` (`STAGE_FUNCS`), a service in `app/services/`, a job state if needed (`models/enums.py` + `shared/schemas/job_states.json`).
* **New timeline op:** add a branch in `services/timeline_service.py::apply_operation` — the editor's `/timeline/ops` endpoint and undo/redo pick it up.
* **New render effect/transition:** extend `workers/rendering/compositor.py` (`_image_motion_filter`, `XFADE_TYPES`) and the `timeline.json` schema.

License: proprietary / all rights reserved unless stated otherwise by the repository owner.
