# Repository Constitution

> Status: Ground truth for this repository
> Purpose: Define how Codebase Gardener should treat this repository while the product is being built.

## Product Identity

Codebase Gardener is an autonomous codebase maintenance engineer delivered first as a sellable GitHub App for 5-100 engineer teams.

It measures, predicts, and reduces codebase degradation while product teams continue shipping features.

## Protected Product Decisions

- V1 optimizes for GitHub App onboarding, hosted Gardener workers, and autonomous maintenance PRs.
- The stack is Python 3.12, Django 5.2 LTS, Django REST Framework, PostgreSQL 16, Redis 7, Celery, React/Vite, TypeScript, TanStack Query/Router, shadcn/ui preset `bLToCnFy`, Lucide Icons, Valibot, TanStack Form, pytest, Playwright, and Vitest.
- Development tooling uses `uv`, `pnpm`, Docker Compose, JSON Schema fixtures, and root `make` commands.
- Implementation is split into three independent lanes: Platform/GitHub App/Dashboard, Repository Intelligence/Constitution/Entropy, and Sessions/PR Automation/Learning.
- Shared JSON contracts in `docs/19-shared-json-contracts.md` are the integration boundary between lanes.
- V1 must support monorepos and logical systems from the start.
- V1 includes light security maintenance, but does not try to compete with full Snyk-style security platforms.
- Repowise should be forked into the project and used as the foundation for repository intelligence.
- Repository Entropy Score is the main metric.
- `GARDENER.md` is the human-readable customer constitution file.
- `.gardener/profile.yaml` is the repo/team memory file.

## Autonomous Fixes Allowed For This Repo

- Documentation updates.
- Agent skill updates.
- Backlog and roadmap refinement.
- Low-risk formatting of authored docs and skill files.

## Autonomous Fixes Not Yet Allowed

- Large implementation decisions without docs alignment.
- Business-model changes without updating `docs/00-product-vision.md` and `docs/14-roadmap.md`.
- Changes that contradict `open-questions-and-clarifying-answers.md` without making the conflict explicit.

## Required Source Truth

Before making product decisions, read the smallest relevant subset of:

- `docs/00-product-vision.md`
- `docs/01-product-domain.md`
- `docs/04-feature-map.md`
- `docs/09-autonomy-and-automation-rules.md`
- `docs/14-roadmap.md`
- `docs/15-epics-and-tasks.md`
- `docs/16-constitution-and-memory-schema.md`
- `docs/17-entropy-signal-catalog.md`
- `docs/18-technical-architecture.md`
- `docs/19-shared-json-contracts.md`
- `open-questions-and-clarifying-answers.md` when resolving ambiguous founder intent

## Ignore

- `.git/**`
- generated dependency directories
- temporary build/test artifacts

## Conflict Rule

If docs, README, GARDENER.md, or prepared clarification answers conflict, stop and ask or document the conflict in the relevant doc before proceeding.
