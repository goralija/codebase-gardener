# Codebase Gardener

Codebase Gardener is an autonomous codebase maintenance engineer for 5-100 engineer teams. V1 is a sellable GitHub App with hosted workers, deterministic source-truth discovery, Repository Entropy Score, focused maintenance PRs, and a dashboard for reports, sessions, and PR outcomes.

Current product truth lives in `docs/`, `GARDENER.md`, and `open-questions-and-clarifying-answers.md`. The original seed specification is archived at `docs/archive/original-seed-spec.md`.

## Foundation Stack

- Python 3.12, Django 5.2 LTS, Django REST Framework, Celery, PostgreSQL 16, Redis 7
- React, Vite, TypeScript, TanStack Query/Router/Form, shadcn/ui preset `bLToCnFy`, Lucide, Valibot
- `uv` for Python workspaces and `pnpm` for frontend/workspace packages
- JSON Schema-backed shared fixtures in `fixtures/`

Use Node 24 for frontend work. The root `package.json` declares the supported range, and local version managers can use `.nvmrc` or `.node-version`.

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

This starts the local product services:

- Django API: `http://localhost:8000`
- Vite dashboard: `http://localhost:5173`

If you only need the frontend shell, run:

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1 pnpm --dir frontend dev --host 0.0.0.0
```

## Local Repowise

Repowise is vendored under `RepoWise/` and tracked by this repository. Edit Repowise files in place, then commit from the Codebase Gardener root:

```bash
git status
git add RepoWise/packages/core/src
git commit -m "Adapt Repowise for Gardener"
```

Use real paths from `git status`; paths like `RepoWise/path/to/changed_file.py` are examples, not literal commands.

Run the vendored Repowise CLI through its project environment:

```bash
uv --project RepoWise run repowise status . --no-workspace
uv --project RepoWise run repowise init . --index-only --mode fast --yes --no-agents --no-codex --no-claude-md
uv --project RepoWise run repowise health . --format json
```

To inspect Repowise's own local dashboard:

```bash
uv --project RepoWise run repowise serve --port 7337 --ui-port 3000
```

Then open `http://localhost:3000`. This dashboard is for debugging raw repository intelligence; the customer-facing product UI remains the Gardener dashboard at `http://localhost:5173`.

Repowise-generated local files such as `.repowise/`, `.codex/`, `.mcp.json`, `RepoWise/.repowise/`, `RepoWise/.venv/`, and `RepoWise/node_modules/` are ignored. Do not commit generated indexes, local virtualenvs, dependency folders, or absolute-path MCP config.

## Three Lanes

- Lane A: Platform, GitHub App, API, Dashboard
- Lane B: Repository Intelligence, Constitution, Entropy
- Lane C: Sessions, PR Automation, Learning

Shared JSON contracts and fixtures are the boundary between lanes. Read `docs/18-technical-architecture.md` and `docs/19-shared-json-contracts.md` before cross-lane work.

Lanes are ownership areas, not long-lived working branches. Read `docs/20-team-working-agreement.md` before starting feature work.
