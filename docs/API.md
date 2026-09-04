# LongForm AI — REST API reference

Generated from the live OpenAPI document (`GET /api/v1/openapi.json`, version 1.0.0). Interactive docs: `/api/v1/docs` (Swagger UI) and `/api/v1/redoc`.

## Conventions

* Base URL: `/api/v1`. All bodies are JSON unless noted (`multipart/form-data` for direct uploads).
* **Auth:** `Authorization: Bearer <access_token>` (from `/auth/signup`, `/auth/login`, `/auth/refresh`) or `X-API-Key: <key>` (Settings → API keys). SSE endpoints additionally accept `?token=<access_token>` because `EventSource` cannot set headers.
* **Errors:** `{ "error": { "code": string, "message": string, "details": object } }` with a matching HTTP status; every response carries `X-Request-ID`. Common codes: `validation_error` (422), `unauthorized` (401), `forbidden` (403), `not_found` (404), `conflict` (409, e.g. stale timeline `base_version` or a job that is already terminal), `insufficient_credits` (402), `provider_error` (502, upstream AI provider failed after retries), `rate_limited` (429).
* **Async work:** generation and render endpoints return `202 Accepted` with a job object; follow progress via `GET /jobs/{id}` or the SSE streams. Pass `idempotency_key` to make retries safe.
* **Pagination:** list endpoints take `page` and `page_size` and return `{ items, total, page, page_size }`.
* **Media URLs:** every `*_url` field is a short-lived signed URL (`SIGNED_URL_EXPIRE_SECONDS`); re-fetch the resource to refresh.

## Realtime events (SSE)

| Stream | Scope |
|---|---|
| `GET /jobs/events` | all jobs of the authenticated user |
| `GET /jobs/projects/{project_id}/events` | jobs of one project |
| `GET /jobs/{job_id}/events` | one job; the server sends `event: done` after the terminal state |

Each `data:` payload is a `ProgressEvent` (`shared/schemas/progress_event.json`): `{ job_id, project_id, job_type, state, progress, stage, message, eta_seconds, result?, error?, ts }`.

## Job states

`QUEUED → PROCESSING → GENERATING_SCRIPT | GENERATING_AUDIO | GENERATING_VISUALS | RENDERING | UPLOADING → COMPLETED | FAILED | CANCELLED` (`shared/schemas/job_states.json`).

## Endpoints

### auth

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/auth/signup` | Signup | SignupRequest | `TokenPair` |
| `POST` | `/api/v1/auth/login` | Login | LoginRequest | `TokenPair` |
| `POST` | `/api/v1/auth/refresh` | Refresh | RefreshRequest | `TokenPair` |
| `POST` | `/api/v1/auth/logout` | Logout |  | `Message` |
| `GET` | `/api/v1/auth/me` | Me |  | `UserPublic` |
| `PATCH` | `/api/v1/auth/me` | Update Me | UserUpdate | `UserPublic` |
| `POST` | `/api/v1/auth/me/password` | Change Password | ChangePasswordRequest | `Message` |
| `GET` | `/api/v1/auth/sessions` | List Sessions |  | `list[SessionPublic]` |
| `DELETE` | `/api/v1/auth/sessions/{session_id}` | Revoke Session |  | `Message` |
| `GET` | `/api/v1/auth/api-keys` | List Api Keys |  | `list[ApiKeyPublic]` |
| `POST` | `/api/v1/auth/api-keys` | Create Key | ApiKeyCreate | `ApiKeyCreated` |
| `DELETE` | `/api/v1/auth/api-keys/{key_id}` | Revoke Key |  | `Message` |

### projects

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/projects` | List Projects | query: `page`, `page_size`, `status`, `q`, `include_archived` | `Page_ProjectSummary_` |
| `POST` | `/api/v1/projects` | Create Project | ProjectCreate | `ProjectDetail` |
| `GET` | `/api/v1/projects/stats` | Project Stats |  | `ProjectStats` |
| `GET` | `/api/v1/projects/{project_id}` | Get Project |  | `ProjectDetail` |
| `PATCH` | `/api/v1/projects/{project_id}` | Update Project | ProjectUpdate | `ProjectDetail` |
| `DELETE` | `/api/v1/projects/{project_id}` | Delete Project | query: `hard` | `Message` |
| `POST` | `/api/v1/projects/{project_id}/restore` | Restore Project |  | `ProjectDetail` |
| `POST` | `/api/v1/projects/{project_id}/duplicate` | Duplicate Project |  | `ProjectDetail` |
| `GET` | `/api/v1/projects/{project_id}/estimate` | Estimate | query: `stages` | `CostEstimate` |
| `POST` | `/api/v1/projects/{project_id}/generate` | Run the full AI pipeline | PipelineRequest | `JobPublic` |
| `GET` | `/api/v1/projects/{project_id}/jobs` | Project Jobs | query: `limit`, `active_only` | `list[JobPublic]` |

### research

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/research` | Get Research |  | `ResearchPublic` |
| `PUT` | `/api/v1/projects/{project_id}/research` | Update Research | ResearchUpdate | `ResearchPublic` |
| `POST` | `/api/v1/projects/{project_id}/research/generate` | Generate Research | ResearchGenerateRequest | `JobPublic` |

### scripts

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/script` | Get Script |  | `ScriptPublic` |
| `PATCH` | `/api/v1/projects/{project_id}/script` | Update Script | ScriptUpdate | `ScriptPublic` |
| `GET` | `/api/v1/projects/{project_id}/script/versions` | Script Versions |  | `list[ScriptPublic]` |
| `POST` | `/api/v1/projects/{project_id}/script/versions/{version}/restore` | Restore Version |  | `ScriptPublic` |
| `GET` | `/api/v1/projects/{project_id}/script/stats` | Script Stats |  | `ScriptStats` |
| `POST` | `/api/v1/projects/{project_id}/script/generate` | Generate Script | ScriptGenerateRequest | `JobPublic` |
| `POST` | `/api/v1/projects/{project_id}/script/sections` | Add Section | SectionCreate | `ScriptPublic` |
| `PATCH` | `/api/v1/projects/{project_id}/script/sections/{section_id}` | Update Section | SectionUpdate | `ScriptPublic` |
| `DELETE` | `/api/v1/projects/{project_id}/script/sections/{section_id}` | Delete Section |  | `ScriptPublic` |
| `POST` | `/api/v1/projects/{project_id}/script/sections/reorder` | Reorder Sections | SectionReorder | `ScriptPublic` |
| `POST` | `/api/v1/projects/{project_id}/script/sections/{section_id}/regenerate` | Regenerate Section | SectionRegenerateRequest | `JobPublic` |
| `POST` | `/api/v1/projects/{project_id}/script/sections/{section_id}/lock` | Toggle Lock | query: `locked` | `Message` |

### scenes

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/scenes` | List Scenes |  | `list[ScenePublic]` |
| `POST` | `/api/v1/projects/{project_id}/scenes` | Create Scene | SceneCreate | `list[ScenePublic]` |
| `POST` | `/api/v1/projects/{project_id}/scenes/generate` | Break the script into scenes | ScenesGenerateRequest | `JobPublic` |
| `POST` | `/api/v1/projects/{project_id}/scenes/visuals/generate` | Generate AI visuals for scenes | VisualGenerateRequest | `JobPublic` |
| `POST` | `/api/v1/projects/{project_id}/scenes/reorder` | Reorder | SceneReorder | `list[ScenePublic]` |
| `GET` | `/api/v1/projects/{project_id}/scenes/{scene_id}` | Get Scene |  | `ScenePublic` |
| `PATCH` | `/api/v1/projects/{project_id}/scenes/{scene_id}` | Update Scene | SceneUpdate | `ScenePublic` |
| `DELETE` | `/api/v1/projects/{project_id}/scenes/{scene_id}` | Delete Scene |  | `list[ScenePublic]` |
| `POST` | `/api/v1/projects/{project_id}/scenes/{scene_id}/split` | Split Scene | SceneSplitRequest | `list[ScenePublic]` |
| `POST` | `/api/v1/projects/{project_id}/scenes/{scene_id}/visual/from-asset` | Use an existing media asset as the scene visual | SceneVisualFromAsset | `ScenePublic` |
| `POST` | `/api/v1/projects/{project_id}/scenes/{scene_id}/visual/from-stock` | Import a stock item and assign it to the scene | SceneVisualFromStock | `ScenePublic` |
| `DELETE` | `/api/v1/projects/{project_id}/scenes/{scene_id}/visual` | Clear Visual |  | `Message` |

### voiceovers

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/voices` | List available TTS voices | query: `language`, `provider` | `list[VoicePublic]` |
| `POST` | `/api/v1/voices/preview` | Synthesize a short preview (returns audio bytes) | VoicePreviewRequest | `object` |
| `GET` | `/api/v1/projects/{project_id}/voiceovers` | List Voiceovers | query: `current_only` | `list[VoiceoverPublic]` |
| `POST` | `/api/v1/projects/{project_id}/voiceovers/generate` | Generate Voiceovers | VoiceoverGenerateRequest | `JobPublic` |
| `GET` | `/api/v1/projects/{project_id}/voiceovers/{voiceover_id}` | Get Voiceover |  | `VoiceoverPublic` |
| `DELETE` | `/api/v1/projects/{project_id}/voiceovers/{voiceover_id}` | Delete Voiceover |  | `object` |

### captions

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/captions` | Get Captions |  | `CaptionPublic` |
| `PUT` | `/api/v1/projects/{project_id}/captions` | Update Captions | CaptionUpdate | `CaptionPublic` |
| `POST` | `/api/v1/projects/{project_id}/captions/generate` | Generate Captions | CaptionGenerateRequest | `JobPublic` |
| `GET` | `/api/v1/projects/{project_id}/captions/export.{fmt}` | Download captions as SRT or VTT |  | `object` |

### timeline

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/projects/{project_id}/timeline` | Get Timeline |  | `TimelinePublic` |
| `PUT` | `/api/v1/projects/{project_id}/timeline` | Save the full timeline document (browser editor) | TimelineSaveRequest | `TimelinePublic` |
| `POST` | `/api/v1/projects/{project_id}/timeline/ops` | Apply a single edit operation server-side | TimelineOpsRequest | `TimelinePublic` |
| `POST` | `/api/v1/projects/{project_id}/timeline/sync` | Rebuild scene-derived tracks from the storyboard | query: `preserve_edits` | `TimelinePublic` |

### jobs

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/jobs` | List Jobs | query: `project_id`, `state`, `active`, `page`, `page_size` | `Page_JobPublic_` |
| `GET` | `/api/v1/jobs/events` | SSE stream of all job events for the current user | query: `token` | `object` |
| `GET` | `/api/v1/jobs/projects/{project_id}/events` | SSE stream of job events for one project | query: `token` | `object` |
| `GET` | `/api/v1/jobs/{job_id}` | Get Job Route |  | `object` |
| `GET` | `/api/v1/jobs/{job_id}/events` | SSE stream for a single job (closes when the job finishes) | query: `token` | `object` |
| `GET` | `/api/v1/jobs/{job_id}/logs` | Job Logs |  | `object` |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Cancel |  | `Message` |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Re-queue a failed or cancelled job |  | `object` |

### media

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/media/uploads/init` | Get a presigned URL to upload a file directly to object storage | UploadInitRequest | `UploadInitResponse` |
| `POST` | `/api/v1/media/uploads/complete` | Register an uploaded object as a media/audio asset | UploadCompleteRequest | `object` |
| `POST` | `/api/v1/media/upload` | Simple multipart upload (small files; proxied through the API) | Body_upload_direct_api_v1_media_upload_post | `object` |
| `GET` | `/api/v1/media` | List Media | query: `project_id`, `kind`, `source`, `q`, `reusable_only`, `page`, `page_size` | `Page_MediaAssetPublic_` |
| `GET` | `/api/v1/media/storage` | Storage Usage |  | `StorageUsage` |
| `GET` | `/api/v1/media/audio` | Music / SFX library (system tracks + your uploads) | query: `kind`, `mood`, `project_id` | `list[AudioAssetPublic]` |
| `DELETE` | `/api/v1/media/audio/{asset_id}` | Delete Audio |  | `Message` |
| `GET` | `/api/v1/media/{asset_id}` | Get Media |  | `MediaAssetPublic` |
| `PATCH` | `/api/v1/media/{asset_id}` | Update Media | MediaUpdate | `MediaAssetPublic` |
| `DELETE` | `/api/v1/media/{asset_id}` | Delete Media |  | `Message` |
| `GET` | `/api/v1/media/stock/search` | Search stock footage/photos through the configured provider | query: `q`, `kind`, `orientation`, `per_page`, `page`, `provider`, `min_duration` | `list[StockSearchResult]` |
| `POST` | `/api/v1/media/stock/import` | Download a stock item into your media library | StockImportRequest | `MediaAssetPublic` |

### usage

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/usage/summary` | Usage Summary | query: `period` | `UsageSummary` |
| `GET` | `/api/v1/usage/records` | Usage Records | query: `kind`, `project_id`, `page`, `page_size` | `Page_UsageRecordPublic_` |
| `GET` | `/api/v1/usage/credits` | Credit ledger | query: `page`, `page_size` | `Page_CreditTransactionPublic_` |
| `GET` | `/api/v1/usage/projects` | Credits spent per project (current period) | query: `period` | `array` |

### billing

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/billing/plans` | List Plans |  | `list[PlanPublic]` |
| `GET` | `/api/v1/billing/subscription` | Get Subscription |  | `SubscriptionPublic` |
| `POST` | `/api/v1/billing/subscription/change` | Change plan (manual mode) or get redirected to checkout (Stripe mode) | ChangePlanRequest | `SubscriptionPublic` |
| `POST` | `/api/v1/billing/subscription/cancel` | Cancel Subscription |  | `SubscriptionPublic` |
| `POST` | `/api/v1/billing/checkout` | Checkout | CheckoutRequest | `CheckoutResponse` |
| `POST` | `/api/v1/billing/credits/purchase` | Buy extra credits (manual mode grants instantly) | CreditPurchaseRequest | `CheckoutResponse` |
| `POST` | `/api/v1/billing/webhooks/stripe` | Stripe webhook receiver |  | `object` |
| `GET` | `/api/v1/billing/portal` | Stripe customer portal link |  | `Message` |

### providers

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/providers` | Available adapters per capability and which one is active |  | `object` |
| `GET` | `/api/v1/providers/health` | Ping every active provider (admin) |  | `object` |
| `GET` | `/api/v1/providers/stats` | Persisted provider usage statistics (admin) |  | `array` |
| `POST` | `/api/v1/providers/sync` | Sync the adapter catalogue into the ai_providers table (admin) |  | `object` |
| `GET` | `/api/v1/providers/{kind}/models` | Models offered by the active adapter of a capability |  | `object` |

### health

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/health` | Liveness/readiness probe |  | `object` |
| `GET` | `/api/v1/health/workers` | Worker health |  | `list[WorkerStatus]` |
| `GET` | `/api/v1/health/queues` | Queue depth and throughput |  | `object` |

### rendering

| Method | Path | Summary | Request | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/render` | Queue a preview or final render | RenderRequest | `RenderJobPublic` |
| `GET` | `/api/v1/projects/{project_id}/renders` | List Renders | query: `limit` | `list[RenderJobPublic]` |
| `GET` | `/api/v1/projects/{project_id}/renders/{render_id}` | Get Render |  | `RenderJobPublic` |
| `GET` | `/api/v1/projects/{project_id}/export` | Signed download URL for the latest final render |  | `object` |

## Schemas

Request/response models are defined with Pydantic in `backend/app/schemas/` and mirrored as TypeScript types in `frontend/src/types/api.ts`. The authoritative, always-current definitions are in the OpenAPI document. Key models:

* **UserPublic** — `id`, `email`, `full_name`, `avatar_url`, `is_verified`, `credits_balance`, `storage_bytes_used`, `preferences`, `created_at`, `last_login_at`
* **TokenPair** — `access_token`, `refresh_token`, `token_type`?, `expires_in`
* **ProjectCreate** — `title`, `topic`, `description`?, `niche`?, `target_audience`?, `language`?, `tone`?, `video_format`?, `target_duration_minutes`?, `aspect_ratio`?, `resolution`?, `visual_style`?, `settings`?
* **ProjectDetail** — `id`, `title`, `topic`, `niche`, `language`, `tone`, `video_format`, `target_duration_minutes`, `aspect_ratio`, `resolution`, `visual_style`, `status`, `thumbnail_url`?, `final_video_url`?, `estimated_duration_seconds`, `created_at`, `updated_at`, `active_job`?, `description`, `target_audience`, `settings`, `thumbnail_asset_id`, `final_video_asset_id`, `last_opened_at`, `counts`?, `pipeline`?
* **ResearchPublic** — `id`, `project_id`, `summary`, `sections`, `key_facts`, `statistics`, `sources`, `suggested_angles`, `keywords`, `provider`, `model`, `approved_at`, `created_at`, `updated_at`
* **ScriptPublic** — `id`, `project_id`, `version`, `is_current`, `title`, `hook`, `outline`, `word_count`, `estimated_duration_seconds`, `target_duration_minutes`, `words_per_minute`, `provider`, `model`, `notes`, `sections`?, `created_at`, `updated_at`
* **ScriptSectionPublic** — `id`, `script_id`, `order_index`, `kind`, `heading`, `content`, `summary`, `talking_points`, `word_count`, `estimated_duration_seconds`, `is_locked`, `regeneration_count`, `updated_at`
* **ScenePublic** — `id`, `project_id`, `section_id`, `order_index`, `title`, `narration`, `visual_description`, `suggested_footage`, `image_prompt`, `video_prompt`, `negative_prompt`, `on_screen_text`, `visual_type`, `duration_seconds`, `transition`, `transition_duration`, `motion_effect`, `music_suggestion`, `music_mood`, `sound_effects`, `keywords`, `visual_asset_id`, `voiceover_id`, `status`, `extra`, `updated_at`, `visual_url`?, `visual_thumbnail_url`?, `visual_kind`?, `voiceover_url`?, `voiceover_duration`?, `voiceover_status`?, `start_time`?
* **VoicePublic** — `id`, `name`, `language`, `gender`, `accent`, `styles`, `preview_url`, `provider`, `is_premium`
* **VoiceoverPublic** — `id`, `project_id`, `scene_id`, `text`, `provider`, `voice_id`, `voice_name`, `language`, `style`, `speed`, `content_type`, `size_bytes`, `duration_seconds`, `word_timings`, `status`, `error`, `is_current`, `created_at`, `url`?
* **TimelinePublic** — `id`, `project_id`, `version`, `fps`, `width`, `height`, `duration_seconds`, `data`, `created_at`, `updated_at`
* **RenderRequest** — `preview`?, `resolution`?, `fps`?, `burn_captions`?, `include_watermark`?, `idempotency_key`?, `range_start`?, `range_end`?
* **RenderJobPublic** — `id`, `project_id`, `job_type`?, `state`, `progress`, `stage`, `message`, `attempt`, `max_attempts`, `cancel_requested`, `params`, `result`, `error`, `eta_seconds`, `credits_reserved`, `credits_charged`, `queued_at`, `started_at`, `finished_at`, `created_at`, `updated_at`, `kind`?, `logs`?, `is_preview`, `width`, `height`, `fps`, `format`, `burn_captions`, `include_watermark`, `output_asset_id`, `output_duration_seconds`, `output_size_bytes`, `render_seconds`, `output_url`?
* **JobPublic** — `id`, `project_id`, `job_type`, `state`, `progress`, `stage`, `message`, `attempt`, `max_attempts`, `cancel_requested`, `params`, `result`, `error`, `eta_seconds`, `credits_reserved`, `credits_charged`, `queued_at`, `started_at`, `finished_at`, `created_at`, `updated_at`, `kind`?, `logs`?
* **MediaAssetPublic** — `id`, `project_id`, `scene_id`, `kind`, `source`, `filename`, `content_type`, `size_bytes`, `width`, `height`, `duration_seconds`, `fps`, `prompt`, `provider`, `tags`, `is_reusable`, `is_uploaded`, `created_at`, `url`?, `thumbnail_url`?
* **AudioAssetPublic** — `id`, `project_id`, `kind`, `source`, `filename`, `content_type`, `size_bytes`, `duration_seconds`, `mood`, `bpm`, `license`, `tags`, `is_system`, `created_at`, `url`?
* **UsageSummary** — `period`, `credits_balance`, `credits_used`, `credits_granted`, `by_kind`, `storage_used_bytes`, `storage_limit_bytes`, `render_minutes`, `videos_completed`, `daily`
* **PlanPublic** — `id`, `name`, `price_usd_month`, `monthly_credits`, `storage_gb`, `max_video_minutes`, `max_resolution`, `watermark`, `concurrent_renders`, `features`, `is_current`?
* **SubscriptionPublic** — `id`, `plan`, `status`, `monthly_credits`, `storage_limit_bytes`, `max_video_minutes`, `max_resolution`, `watermark_required`, `concurrent_renders`, `current_period_start`, `current_period_end`, `cancel_at_period_end`, `payment_provider`
* **CheckoutResponse** — `checkout_url`, `mode`, `message`
* **PipelineRequest** — `stages`?, `skip_existing`?, `render_preview`?, `idempotency_key`?
* **WorkerStatus** — `worker_id`, `hostname`, `queues`, `concurrency`, `active_tasks`, `processed_total`, `failed_total`, `last_heartbeat_at`, `healthy`, `version`
