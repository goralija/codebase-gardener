.PHONY: setup services dev backend-dev frontend-dev check backend-check backend-test analysis-test fixtures-validate docs-skills-validate frontend-lint frontend-test frontend-build frontend-e2e
.PHONY: services-check runtime-check backend-migrate

PYTHON_VERSION ?= 3.12
DOCKER ?= docker
VITE_API_BASE_URL ?= http://localhost:8000/api/v1

setup:
	uv sync --python $(PYTHON_VERSION) --all-packages --all-groups
	pnpm install
	pnpm --dir frontend exec playwright install chromium

services:
	$(DOCKER) compose up -d --wait postgres redis

services-check:
	$(DOCKER) compose config --quiet

runtime-check: services backend-migrate backend-check

dev: services
	$(MAKE) -j2 backend-dev frontend-dev

backend-dev:
	cd backend && uv run python manage.py runserver 0.0.0.0:8000

frontend-dev:
	VITE_API_BASE_URL=$(VITE_API_BASE_URL) pnpm --dir frontend dev --host 0.0.0.0

check: services-check fixtures-validate docs-skills-validate backend-check backend-test analysis-test frontend-lint frontend-test frontend-build frontend-e2e

backend-check:
	cd backend && uv run python manage.py check

backend-migrate:
	cd backend && uv run python manage.py migrate --noinput

backend-test:
	cd backend && uv run pytest

analysis-test:
	cd analysis_engine && uv run pytest

fixtures-validate:
	uv run python scripts/validate_fixtures.py

docs-skills-validate:
	uv run python scripts/validate_docs_and_skills.py

frontend-test:
	pnpm --dir frontend test:run

frontend-lint:
	pnpm --dir frontend lint

frontend-build:
	pnpm --dir frontend build

frontend-e2e:
	pnpm --dir frontend exec playwright test
