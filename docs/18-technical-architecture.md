# Technical Architecture

> Status: Ground truth
> Purpose: Lock the implementation stack, ownership lanes, and cross-lane contracts.

## Stack decision

Codebase Gardener uses this stack:

- Backend/API/workers: Python, Django, Django REST Framework, PostgreSQL.
- Queue/workers: Redis and Celery.
- Analysis engine: Python package wrapping the Repowise fork.
- Frontend: React, Vite, TypeScript, TanStack Query, TanStack Router, shadcn/ui preset `bLToCnFy`, Lucide Icons, Valibot, and TanStack Form.
- GitHub integration: GitHub REST through Python HTTP clients.
- Storage: PostgreSQL for product and session data; object storage later for large artifacts.
- Testing: pytest, Playwright, and Vitest.
- Tooling: `uv`, `pnpm`, Docker Compose, JSON Schema fixtures, and root `make` commands.

## Repository layout target

Initial implementation should converge on:

```text
Makefile
compose.yaml
pyproject.toml
pnpm-workspace.yaml
backend/
  config/
  apps/
    accounts/
    github_app/
    repositories/
    constitution/
    analysis/
    entropy/
    sessions/
    maintenance_prs/
    billing/
  workers/
analysis_engine/
  src/gardener_analysis/
frontend/
  src/
    routes/
    features/
    components/
    lib/
fixtures/
  contracts/
  schemas/
  repos/
docs/
```

## Three implementation lanes

### Lane A - Platform, GitHub App, API, Dashboard

Owns:

- Django/DRF project foundation.
- Postgres models and migrations for product/session data.
- GitHub App installation and webhook ingestion.
- Organization/repository access and permissions.
- Dashboard shell and API integration.
- Displaying mocked and real reports.

Primary docs:

- `docs/06-github-app-api-spec.md`
- `docs/07-data-storage-rules.md`
- `docs/08-ui-ux-guidelines.md`
- `docs/10-integrations.md`
- `docs/13-deployment-and-environments.md`

### Lane B - Repository Intelligence, Constitution, Entropy

Owns:

- Python analysis package wrapping Repowise.
- Fixture repositories.
- Source-truth discovery.
- Repository Constitution model.
- Entropy scoring and forecasts.
- Architecture violations and analysis snapshots.

Primary docs:

- `docs/16-constitution-and-memory-schema.md`
- `docs/17-entropy-signal-catalog.md`
- `docs/19-shared-json-contracts.md`

### Lane C - Sessions, PR Automation, Learning

Owns:

- Celery session lifecycle.
- Trigger policies.
- Opportunity ranking.
- Maintenance PR planning and GitHub branch/PR actions.
- `.gardener/profile.yaml` learning.
- ROI estimates and session reports.

Primary docs:

- `docs/05-user-flows.md`
- `docs/09-autonomy-and-automation-rules.md`
- `docs/19-shared-json-contracts.md`

## Branch workflow

Lanes are ownership boundaries, not long-lived implementation branches. Feature work should use short atomic branches from latest `main`, following `docs/20-team-working-agreement.md`.

## Parallelization rule

The three lanes must depend on shared JSON contracts before depending on each other's implementation. When a lane needs another lane's output, it should consume a fixture JSON contract first, then switch to the real service later.

Examples:

- Lane A can build the first-report dashboard from `EntropyReport` and `GardeningSessionResult` fixtures before Lane B and Lane C are complete.
- Lane B can produce `AnalysisSnapshot`, `RepositoryConstitution`, and `EntropyReport` fixtures without GitHub App onboarding.
- Lane C can plan PRs from `MaintenanceOpportunity` fixtures before real GitHub webhooks are implemented.

## Contract ownership

Shared contract shapes live in `docs/19-shared-json-contracts.md`.

Implementation should encode the same shapes in:

- JSON Schemas and valid sample fixtures in `fixtures/`.
- DRF serializers for API input/output.
- Python dataclasses or Pydantic-style internal objects where helpful in `analysis_engine/`.
- TypeScript types generated from API schema or manually mirrored until generation exists.

Contract changes must be reviewed across all three lanes before implementation work continues.
