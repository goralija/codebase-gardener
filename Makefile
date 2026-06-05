.PHONY: setup services dev backend-dev frontend-dev check backend-check backend-test analysis-test fixtures-validate frontend-lint frontend-test frontend-build frontend-e2e

PYTHON_VERSION ?= 3.12

setup:
	uv sync --python $(PYTHON_VERSION) --all-packages --all-groups
	pnpm install
	pnpm --dir frontend exec playwright install chromium

services:
	docker compose up -d postgres redis

dev: services
	$(MAKE) -j2 backend-dev frontend-dev

backend-dev:
	cd backend && uv run python manage.py runserver 0.0.0.0:8000

frontend-dev:
	pnpm --dir frontend dev --host 0.0.0.0

check: fixtures-validate backend-check backend-test analysis-test frontend-lint frontend-test frontend-build frontend-e2e

backend-check:
	cd backend && uv run python manage.py check

backend-test:
	cd backend && uv run pytest

analysis-test:
	cd analysis_engine && uv run pytest

fixtures-validate:
	uv run python scripts/validate_fixtures.py

frontend-test:
	pnpm --dir frontend test:run

frontend-lint:
	pnpm --dir frontend lint

frontend-build:
	pnpm --dir frontend build

frontend-e2e:
	pnpm --dir frontend exec playwright test
