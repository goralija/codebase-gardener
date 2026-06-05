---
name: testing
description: Use before marking Codebase Gardener work complete, and when adding tests for constitution parsing, entropy scoring, GitHub App behavior, hosted sessions, PR safety, dashboards, integrations, or docs/skills.
---

# Testing Skill

Use this skill before finishing implementation work.

## Required context

Read `docs/12-testing-strategy.md` first.

## Mandatory standard

Work is done only when relevant checks are satisfied:

- Constitution behavior is tested when source truth changes.
- Entropy scoring is tested when signals, weights, thresholds, or forecasts change.
- GitHub App webhooks and permissions are tested when provider behavior changes.
- Hosted sessions are tested when triggers, lifecycle, workers, or PR selection changes.
- Protected-module and confidence gates are tested when PR behavior changes.
- UI states are tested when dashboard behavior changes.
- Shared JSON fixtures and contracts are tested when lane boundaries change.
- Docs and skills are validated when documentation/skill files change.

## Test selection guide

- Constitution: fixture repos with complete, missing, and conflicting source truth.
- Entropy: synthetic signal inputs and fixture repos.
- GitHub App: webhook signature, replay/idempotency, installation scope, repository access.
- Sessions: trigger, policy, lifecycle, failure, non-conflicting PR selection.
- PR safety: confidence threshold, protected paths, PR body evidence, draft/autonomous split.
- Security: customer isolation, token handling, secret logging, audit events.

## Completion response

Report what was tested and any tests that could not be run. Do not claim full verification if relevant checks were skipped.
