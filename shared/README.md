# shared/

Language-agnostic contracts shared between the FastAPI backend, the Celery workers
and the Next.js frontend.

| File | Purpose |
| --- | --- |
| `schemas/job_states.json` | Canonical job lifecycle states + progress weights used for ETA calculation |
| `schemas/progress_event.json` | Shape of realtime progress events (Redis pub/sub → SSE → browser) |
| `schemas/timeline.json` | The timeline document that the browser editor produces and the FFmpeg compositor consumes |
| `types/` | Generated/handwritten TypeScript mirrors (`frontend/src/types` imports from here via `@shared/*`) |

Python mirrors live in `backend/app/models/enums.py` and `backend/app/schemas/timeline.py`.
TypeScript mirrors live in `frontend/src/types/`.

A CI check (`infrastructure/scripts/check_contracts.py`) verifies the enum lists stay in sync.
