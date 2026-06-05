# Team Working Agreement

> Status: Ground truth
> Purpose: Define how the three-person team should work with minimal drift during fast feature development.

## Goal

Ship real product behavior quickly without creating long-lived integration drift, hidden contract changes, or hard-to-review agent output.

## Branch Model

`main` is the only integration branch. Lanes are ownership areas, not long-lived working branches.

Every implementation task starts from latest `main`:

```bash
git fetch origin
git switch main
git pull --ff-only
git switch -c codex/e04-t03-session-lifecycle-fixtures
```

Use one short branch per atomic change. Prefer task IDs in branch names:

- `codex/e02-t01-api-foundation`
- `codex/e03-t03-source-truth-discovery`
- `codex/e04-t04-pr-planning-policy`

Avoid branches that try to contain an entire lane, dashboard, analysis engine, or worker system.

## Work Rhythm

Start each work block from current `main` and run the base checks:

```bash
git fetch origin
git switch main
git pull --ff-only
make check
```

Before opening a PR:

```bash
make check
```

When runtime services, Django settings, Docker Compose, migrations, or worker wiring change:

```bash
DOCKER="docker --context desktop-linux" make runtime-check
```

If `main` changes while a branch is active, rebase and rerun checks:

```bash
git fetch origin
git rebase origin/main
make check
```

## Shared Contract Rule

The cross-lane boundary is:

```text
fixtures/schemas/
fixtures/contracts/
docs/19-shared-json-contracts.md
```

Any change to those files must be small, announced to the team, and reviewed across all active lanes before dependent implementation continues.

## Lane Assignment

Lane A owns platform, GitHub App, API, and dashboard work.

Lane B owns repository intelligence, source-truth discovery, Repository Constitution, entropy scoring, and maintenance opportunities. Lane B is the highest-complexity lane and should be owned by the strongest technical/domain person.

Lane C owns hosted sessions, PR planning, and learning. During the hackathon, the least experienced person should start in Lane C on fixture-first tasks only:

- `E04-T01` Celery worker foundation with review
- `E04-T03` session lifecycle from shared fixtures
- `E04-T04` focused PR planning from fixture opportunities
- `E04-T07` ROI estimates

Do not assign `E04-T05` GitHub branch and PR execution to the least experienced person until the fixture-first session and PR planning behavior is tested and reviewed.

## PR Standard

Every PR must explain:

- what changed
- why it matters
- which checks ran
- whether shared contracts changed
- any assumptions or blockers

Keep PRs small enough that a teammate can review them quickly during the hackathon.

## Conflict Hotspots

Coordinate before editing:

```text
fixtures/schemas/*
fixtures/contracts/*
docs/19-shared-json-contracts.md
backend/config/settings.py
Makefile
compose.yaml
frontend/src/App.tsx
```

When a shared file must change, merge the shared-contract or setup PR first, then have everyone rebase from `main`.
