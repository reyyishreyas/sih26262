SHELL := /bin/bash
PYTHON ?= .venv/bin/python
COMPOSE ?= docker compose

.PHONY: help setup dev up down reset logs ps lint test build migrate seed smoke verify-isolation migrate-sqlite prod-config retention loadtest

help:
	@echo "SIH26262 developer commands"
	@echo "  make setup             one-time setup: packages, config, demo data (~5 min)"
	@echo "  make dev               start the API and UI together (Ctrl-C stops both)"
	@echo "  make up                build and start the full PostgreSQL stack"
	@echo "  make down              stop the stack, keep volumes"
	@echo "  make reset             stop and DELETE volumes, then start fresh"
	@echo "  make logs              follow API/worker/db logs"
	@echo "  make ps                show container health"
	@echo "  make lint              run Ruff over backend code"
	@echo "  make test              run the backend test suite"
	@echo "  make build             type-check/build the frontend"
	@echo "  make prod-config       validate docker-compose.prod.yml (needs .env.production)"
	@echo "  make smoke             exercise the running stack end to end"
	@echo "  make verify-isolation  prove PostgreSQL role isolation"
	@echo "  make migrate-sqlite    run Alembic against a throwaway SQLite file"
	@echo "  make retention         report retention-eligible transient rows (dry run)"
	@echo "  make loadtest          run a bounded read-only load probe"

setup:
	./scripts/setup.sh

dev:
	./scripts/dev.sh

up:
	$(COMPOSE) up -d --build
	@echo "API  http://localhost:8000  (explorer /docs off unless SIH_DOCS_ENABLED=true)"
	@echo "UI   http://localhost:5173"

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build

logs:
	$(COMPOSE) logs -f api worker db

ps:
	$(COMPOSE) ps

lint:
	cd backend && ../$(PYTHON) -m ruff check app tests migrations scripts

test:
	cd backend && ../$(PYTHON) -m pytest -q

build:
	cd frontend && npm run build

prod-config:
	docker compose --env-file .env.production -f docker-compose.prod.yml config >/dev/null
	@echo "docker-compose.prod.yml is valid"

migrate:
	$(COMPOSE) run --rm migrate

seed:
	cd backend && ../$(PYTHON) -m app.services.seed

smoke:
	./scripts/smoke.sh

verify-isolation:
	cd backend && ../$(PYTHON) -m scripts.verify_isolation

migrate-sqlite:
	cd backend && rm -f /tmp/sih26262-migrate.db \
		&& SIH_DATABASE_URL=sqlite:////tmp/sih26262-migrate.db ../$(PYTHON) -m alembic upgrade head \
		&& SIH_DATABASE_URL=sqlite:////tmp/sih26262-migrate.db ../$(PYTHON) -m alembic check
