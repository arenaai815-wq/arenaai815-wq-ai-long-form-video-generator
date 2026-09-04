# Convenience targets. See README.md for details.
COMPOSE := docker compose -f infrastructure/docker-compose.yml
PY      := backend/.venv/bin/python
export PYTHONPATH := $(CURDIR):$(CURDIR)/backend

.PHONY: help bootstrap dev api worker web infra up down logs migrate migration seed test lint build

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

bootstrap:       ## Install backend + frontend deps, create .env, migrate, seed
	./infrastructure/scripts/bootstrap.sh

dev:             ## Run API + worker + frontend locally (needs Postgres/Redis, see `make infra`)
	./infrastructure/scripts/dev.sh
api:             ## Run only the API (reload)
	./infrastructure/scripts/dev.sh api
worker:          ## Run only a Celery worker (+beat)
	./infrastructure/scripts/dev.sh worker
web:             ## Run only the Next.js dev server
	./infrastructure/scripts/dev.sh web

infra:           ## Start Postgres, Redis and MinIO in Docker for local development
	$(COMPOSE) up -d postgres redis minio minio-init
up:              ## Build and start the whole stack in Docker
	$(COMPOSE) up --build -d
down:            ## Stop the Docker stack
	$(COMPOSE) down
logs:            ## Tail Docker logs
	$(COMPOSE) logs -f --tail=200

migrate:         ## Apply database migrations
	cd backend && $(CURDIR)/$(PY) -m alembic upgrade head
migration:       ## Create a new migration: make migration m="add foo"
	cd backend && $(CURDIR)/$(PY) -m alembic revision --autogenerate -m "$(m)"
seed:            ## Seed plans + admin user
	cd backend && $(CURDIR)/$(PY) -m scripts.seed

test:            ## Backend tests
	cd backend && $(CURDIR)/$(PY) -m pytest -q
lint:            ## Lint backend (ruff) and frontend (eslint + tsc)
	cd backend && $(CURDIR)/$(PY) -m ruff check app ../workers
	cd frontend && npx tsc --noEmit -p . && npm run lint
build:           ## Production build of the frontend
	cd frontend && npm run build
