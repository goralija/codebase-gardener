# Testing Strategy

> Status: Ground truth
> Purpose: Define the verification standard for AI-assisted product development.

## Product testing principles

Gardener is trust-sensitive. Tests must focus on avoiding unsafe PRs, incorrect source-truth interpretation, bad scoring, customer data leaks, and webhook/session mistakes.

Use:

- pytest for Django, analysis package, Celery, and backend integration tests
- Vitest for React components, hooks, and frontend utilities
- Playwright for critical dashboard and onboarding flows

## Foundation commands

- `make setup`: install Python and frontend dependencies and Playwright Chromium.
- `make services`: start local PostgreSQL 16 and Redis 7 through Docker Compose.
- `make check`: run fixture validation, backend checks/tests, analysis tests, frontend lint/Vitest/build, and Playwright smoke.

## Required test areas

### Repository Constitution

- file discovery precedence and coverage
- conflict detection
- onboarding question generation
- protected module parsing
- allowed fix parsing
- ignored path parsing
- learned memory never overriding explicit rules

### Entropy scoring

- component weights
- repo/system/module/file scoring
- threshold classification
- trend calculation
- forecast output
- score explanation and evidence traceability

### Gardening sessions

- triggers
- lifecycle phase transitions
- policy checks before execution
- non-conflicting PR selection
- failure recovery
- session reports

### GitHub App

- webhook signature verification
- installation scoping
- repository access checks
- branch and PR creation
- PR outcome ingestion
- idempotency for repeated webhooks

### Shared JSON contracts

- JSON Schema fixture shape validation
- DRF serializer output compatibility
- frontend fixture consumption
- analysis package output compatibility
- session worker input compatibility

### Security

- organization/repository isolation
- token protection
- no secret logging
- blocked protected-module modifications
- audit events for sensitive settings

## CI rules

Before marking implementation work complete:

- run relevant unit tests
- run integration tests for GitHub/session changes
- run lint/format checks when configured
- run UI tests for dashboard changes
- run docs validation for docs/skill changes

## Documentation rule

Update docs when product truth, safety policy, scoring behavior, architecture, API, storage, or roadmap changes.
