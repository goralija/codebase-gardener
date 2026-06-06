.PHONY: setup services dev backend-dev frontend-dev worker-dev check backend-check backend-test analysis-test fixtures-validate docs-skills-validate frontend-lint frontend-test frontend-build frontend-e2e
.PHONY: services-check runtime-check backend-migrate

PYTHON_VERSION ?= 3.12
DOCKER ?= docker
COMPOSE ?= $(shell if $(DOCKER) compose version >/dev/null 2>&1; then printf '$(DOCKER) compose'; fi)
PNPM ?= corepack pnpm
VITE_API_BASE_URL ?= http://localhost:8000/api/v1

setup:
	uv sync --python $(PYTHON_VERSION) --all-packages --all-groups
	$(PNPM) install
	$(PNPM) --dir frontend exec playwright install chromium

services:
	@if [ -n "$(COMPOSE)" ]; then \
		$(COMPOSE) up -d --wait postgres redis; \
	else \
		DOCKER="$(DOCKER)" scripts/start_services_with_docker.sh; \
	fi

services-check:
	@if [ -n "$(COMPOSE)" ]; then \
		$(COMPOSE) config --quiet; \
	else \
		$(DOCKER) info >/dev/null 2>&1 || { \
			echo "Docker daemon is not reachable. Start Docker or run with a Docker command that has socket access."; \
			exit 1; \
		}; \
	fi

runtime-check: services backend-migrate backend-check

dev: services
	$(MAKE) -j2 backend-dev frontend-dev

backend-dev:
	cd backend && uv run python manage.py runserver 0.0.0.0:8000

worker-dev:
	cd backend && uv run celery -A config worker -l INFO

frontend-dev:
	VITE_API_BASE_URL=$(VITE_API_BASE_URL) $(PNPM) --dir frontend dev --host 0.0.0.0

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
	$(PNPM) --dir frontend test:run

frontend-lint:
	$(PNPM) --dir frontend lint

frontend-build:
	$(PNPM) --dir frontend build

frontend-e2e:
	$(PNPM) --dir frontend exec playwright test
