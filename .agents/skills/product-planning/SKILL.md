---
name: product-planning
description: Use when planning Codebase Gardener features, deciding product scope, turning requests into implementation-ready requirements, or checking whether work fits the autonomous codebase maintenance engineer direction.
---

# Product Planning Skill

Use this skill before implementing new product behavior or changing feature scope.

## Required context

Read these docs first:

1. `docs/00-product-vision.md`
2. `docs/01-product-domain.md`
3. `docs/04-feature-map.md`
4. `docs/05-user-flows.md`
5. `docs/14-roadmap.md`
6. `docs/18-technical-architecture.md`
7. `docs/19-shared-json-contracts.md` when planning cross-lane behavior
8. `docs/15-epics-and-tasks.md` when planning backlog work

## Product rules

- Treat Codebase Gardener as an autonomous codebase maintenance engineer.
- Optimize v1 for a sellable GitHub App experience for 5-100 engineer teams.
- Make the product useful through focused maintenance PRs, not dashboard-only reporting.
- Use deterministic source truth before agent inference.
- Use Repowise-derived repository intelligence as the foundation.
- Support monorepos and logical systems from the start.
- Keep implementation split into Lane A, Lane B, and Lane C with shared JSON contracts as the boundary.
- Include light security maintenance, but do not position v1 as a full security platform.
- Avoid large risky rewrites and "make the repo perfect" behavior.

## Planning workflow

1. Restate the request as a product goal.
2. Identify the target user and maintenance pain.
3. Map the request to docs, entities, permissions, triggers, entropy signals, constitution rules, and PR safety policy.
4. Define MVP scope and explicit non-goals.
5. Identify affected docs, skills, tests, and backlog tasks.
6. Produce implementation-ready requirements.

## Output format

```md
## Goal

## Primary user

## Maintenance value

## Scope

## Non-goals

## Affected docs

## Affected entities

## Constitution impact

## Entropy impact

## Autonomy / PR safety

## Acceptance criteria

## Required tests
```

## Stop conditions

Ask for clarification if the request conflicts with `GARDENER.md`, requires risky autonomous changes, contradicts founder answers in `open-questions-and-clarifying-answers.md`, or changes v1 away from GitHub App first.
