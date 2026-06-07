# Deployment and Environments

> Status: Ground truth
> Purpose: Define deployment expectations for the hosted GitHub App product.

## V1 deployment model

V1 is Gardener-hosted:

- hosted web dashboard
- hosted Django/DRF API
- hosted Celery background workers
- hosted scheduler
- hosted PostgreSQL database
- hosted Redis broker/cache
- GitHub App integration

Customer-hosted/local deployment is not part of the standard v1 offer. It may be offered later for large customers that demand it.

## Environments

- Development: local engineering environment.
- Staging: connected to a staging GitHub App and non-production data.
- Production: connected to production GitHub App installations.

## Required services

The chosen stack must support:

- GitHub webhook ingestion
- Celery background jobs
- scheduled jobs through Celery Beat or an equivalent scheduler
- secure token storage
- persistent analysis snapshots
- promoted repository analysis baselines
- repository checkout or API-based file access
- hosted dashboard/API
- logs, metrics, and error tracking

## Local development services

The default Docker Compose host ports are `15432` for PostgreSQL and `16379` for Redis to avoid collisions with common local services. Developers may override `POSTGRES_PORT`, `REDIS_PORT`, `DATABASE_URL`, and `REDIS_URL` per worktree or machine.

Start the local product stack from the repository root:

```bash
make setup
make services
make dev
```

`make dev` applies Django migrations, then runs the Django API at
`http://localhost:8000`, the Celery worker, the Vite dashboard at
`http://localhost:5173`, and a Cloudflare Quick Tunnel for local GitHub webhook
testing when `cloudflared` is installed. The tunnel output includes the full
GitHub App webhook URL for `/api/v1/github-app/webhooks/`. Quick Tunnel
hostnames are temporary and usually change each run; staging and production must
use stable hostnames.

Lane B repository-intelligence development uses the vendored Repowise checkout at `RepoWise/`. Run it through its own project environment from the Codebase Gardener root:

```bash
uv --project RepoWise run repowise status . --no-workspace
uv --project RepoWise run repowise init . --index-only --mode fast --yes --no-agents --no-codex --no-claude-md
uv --project RepoWise run repowise health . --format json
```

To test Repowise against a Lane B fixture repository without dirtying tracked fixture files, copy the fixture into a temporary Git repository and scan the temporary checkout:

```bash
PROJECT=/Users/bloomteq/codebase-gardener
FIXTURE=normal_repo
tmpdir=$(mktemp -d /tmp/gardener-fixture-${FIXTURE}.XXXXXX)

cp -R "$PROJECT/fixtures/repos/$FIXTURE/." "$tmpdir"

git -C "$tmpdir" init
git -C "$tmpdir" add .
git -C "$tmpdir" -c user.name="Fixture Test" -c user.email="fixture@example.com" commit -m "Initial fixture repo"

uv --project "$PROJECT/RepoWise" run repowise init "$tmpdir" \
  --index-only \
  --mode fast \
  --yes \
  --no-agents \
  --no-codex \
  --no-claude-md \
  --no-distill-hook

uv --project "$PROJECT/RepoWise" run repowise status "$tmpdir" --no-workspace
```

Supported fixture names are `normal_repo`, `monorepo_repo`, `missing_docs_repo`, `conflicting_docs_repo`, and `protected_modules_repo`.

Repowise's own dashboard can be started for debugging raw scan output:

```bash
uv --project RepoWise run repowise serve --port 7337 --ui-port 3000
```

Open `http://localhost:3000` for the Repowise dashboard. This is an engineering/debugging surface only; Gardener's product dashboard remains the Vite app.

Repowise source files under `RepoWise/` are tracked in the Codebase Gardener repository. Generated local files and machine-specific config are ignored, including `.repowise/`, `.codex/`, `.mcp.json`, `RepoWise/.repowise/`, `RepoWise/.venv/`, and `RepoWise/node_modules/`.

## Worker requirements

- Isolate customer sessions.
- Limit runtime and resource usage.
- Clean up temporary repository checkouts.
- Avoid cross-customer cache leakage.
- Persist failures with enough detail to debug without leaking code or secrets.
- Promote baselines only after the intended lifecycle checkpoint: first scan,
  completed non-first-scan session, or post-PR refresh.
- Run post-PR refresh idempotently after all Gardener-authored PRs for a
  session are merged, closed, or later reverted.

## Monitoring

Track:

- webhook failures
- session durations
- worker failures
- PR creation failures
- scoring failures
- GitHub API rate limit pressure
- customer-facing latency
- entropy report generation time
- baseline promotion and post-PR refresh failures

## Implementation stack

The implementation stack is fixed in `docs/18-technical-architecture.md`. The concrete hosting provider remains open.
