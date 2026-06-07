.PHONY: setup services dev backend-dev frontend-dev cloudflare-tunnel-dev worker-dev check backend-check backend-test analysis-test fixtures-validate docs-skills-validate frontend-lint frontend-test frontend-build frontend-e2e
.PHONY: services-check runtime-check backend-migrate

PYTHON_VERSION ?= 3.12
DOCKER ?= docker
COMPOSE ?= $(shell if $(DOCKER) compose version >/dev/null 2>&1; then printf '$(DOCKER) compose'; fi)
PNPM ?= corepack pnpm
VITE_API_BASE_URL ?= http://localhost:8000/api/v1
CLOUDFLARED ?= cloudflared
CLOUDFLARE_TUNNEL_URL ?= http://localhost:8000
CLOUDFLARE_TUNNEL_HOST_HEADER ?= localhost:8000
CLOUDFLARE_TUNNEL_TRANSPORT_LOGLEVEL ?= fatal
GITHUB_WEBHOOK_PATH ?= /api/v1/github-app/webhooks/

setup:
	uv sync --python $(PYTHON_VERSION) --all-packages --all-groups
	$(PNPM) install
	$(PNPM) --dir frontend exec playwright install chromium

services:
	@if [ -n "$(COMPOSE)" ]; then \
		$(COMPOSE) up -d --wait postgres redis minio; \
		$(COMPOSE) run --rm minio-setup; \
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

dev: services backend-migrate
	$(MAKE) -j4 backend-dev worker-dev frontend-dev cloudflare-tunnel-dev

backend-dev:
	cd backend && uv run python manage.py runserver 0.0.0.0:8000

worker-dev:
	cd backend && uv run celery -A config worker -l INFO

frontend-dev:
	VITE_API_BASE_URL=$(VITE_API_BASE_URL) $(PNPM) --dir frontend dev --host 0.0.0.0

cloudflare-tunnel-dev:
	scripts/run_cloudflare_quick_tunnel.sh "$(CLOUDFLARED)" "$(CLOUDFLARE_TUNNEL_URL)" "$(CLOUDFLARE_TUNNEL_HOST_HEADER)" "$(GITHUB_WEBHOOK_PATH)" "$(CLOUDFLARE_TUNNEL_TRANSPORT_LOGLEVEL)"

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
