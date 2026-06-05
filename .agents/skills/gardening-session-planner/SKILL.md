---
name: gardening-session-planner
description: Use when designing or implementing Gardening Session triggers, lifecycle, hosted worker behavior, opportunity ranking, execution planning, session reports, or learning loops.
---

# Gardening Session Planner Skill

Use this skill for work around the core run loop.

## Required context

Read these docs first:

1. `docs/05-user-flows.md`
2. `docs/09-autonomy-and-automation-rules.md`
3. `docs/13-deployment-and-environments.md`
4. `docs/15-epics-and-tasks.md`
5. `docs/18-technical-architecture.md`
6. `docs/19-shared-json-contracts.md`
7. `docs/17-entropy-signal-catalog.md`

Read `docs/16-constitution-and-memory-schema.md` when a session depends on source truth, protected modules, or memory.

## Lifecycle

Every session must follow:

1. Observe
2. Diagnose
3. Forecast
4. Plan
5. Execute
6. Learn

## Trigger rules

V1 triggers are:

- manual
- schedule
- after N commits
- risky module changed
- PR opened
- CI failure

Celery hosted workers run sessions. Each session must be scoped to one managed repository and a specific trigger event.

## Planning workflow

1. Load repository policy and constitution.
2. Determine trigger reason and scope.
3. Gather current repository intelligence or fixture contracts.
4. Diagnose entropy contributors and violations.
5. Forecast risk and rank opportunities.
6. Split selected work into non-conflicting focused PR candidates.
7. Apply autonomy and confidence policy.
8. Produce session report and execution plan.
9. Record learning inputs from PR outcomes.

## Safety checks

- Do not execute if critical constitution conflicts are unresolved.
- Do not create PRs below confidence threshold.
- Do not create overlapping PRs.
- Do not touch never-touch paths.
- Defer work that depends on another PR in the same session.

## Done criteria

- Session output is deterministic for the same inputs.
- Failures are visible and recoverable.
- Session report explains deferred and executed work.
- Tests cover trigger, policy, conflict, and failure paths.
