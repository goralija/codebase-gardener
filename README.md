# Codebase Gardener

Codebase Gardener is an autonomous codebase maintenance engineer for 5-100 engineer teams. V1 is a sellable GitHub App with hosted workers, deterministic source-truth discovery, Repository Entropy Score, focused maintenance PRs, and a dashboard for reports, sessions, and PR outcomes.

Current product truth lives in `docs/`, `GARDENER.md`, and `open-questions-and-clarifying-answers.md`. The original seed specification is archived at `docs/archive/original-seed-spec.md`.

## Foundation Stack

- Python 3.12, Django 5.2 LTS, Django REST Framework, Celery, PostgreSQL 16, Redis 7
- React, Vite, TypeScript, TanStack Query/Router/Form, shadcn/ui preset `bLToCnFy`, Lucide, Valibot
- `uv` for Python workspaces and `pnpm` for frontend/workspace packages
- JSON Schema-backed shared fixtures in `fixtures/`

## Start Here

```bash
make setup
make services
make check
```

If Docker is running under a non-default context, pass it through `DOCKER`:

```bash
DOCKER="docker --context desktop-linux" make services
```

The default service ports avoid common local PostgreSQL and Redis conflicts:

- PostgreSQL: host `15432` -> container `5432`
- Redis: host `16379` -> container `6379`

Override `POSTGRES_PORT`, `REDIS_PORT`, `DATABASE_URL`, and `REDIS_URL` in `.env` when a worktree or machine needs different ports.

For active development:

```bash
make dev
```

## Three Lanes

- Lane A: Platform, GitHub App, API, Dashboard
- Lane B: Repository Intelligence, Constitution, Entropy
- Lane C: Sessions, PR Automation, Learning

Shared JSON contracts and fixtures are the boundary between lanes. Read `docs/18-technical-architecture.md` and `docs/19-shared-json-contracts.md` before cross-lane work.
