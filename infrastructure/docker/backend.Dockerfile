# syntax=docker/dockerfile:1.7
# Shared image for the FastAPI API and the Celery workers (same code, different command).
# Build from the repo root:  docker build -f infrastructure/docker/backend.Dockerfile .
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/backend \
    FFMPEG_BINARY=/usr/bin/ffmpeg \
    FFPROBE_BINARY=/usr/bin/ffprobe \
    FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf

# ffmpeg (with libx264/aac/libass for subtitles), fonts for captions/text cards, curl for healthchecks
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fontconfig curl tini \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/
COPY workers/ workers/
COPY shared/ shared/
COPY infrastructure/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /app/data/storage /app/data/work && chown -R app:app /app

USER app
WORKDIR /app/backend
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]

# ---------------------------------------------------------------------------
FROM base AS api
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/v1/health || exit 1
CMD ["api"]

# ---------------------------------------------------------------------------
FROM base AS worker
HEALTHCHECK --interval=60s --timeout=20s --start-period=30s --retries=3 \
  CMD celery -A workers.celery_app:celery_app inspect ping -d "celery@$(hostname)" --timeout 10 || exit 1
CMD ["worker"]
