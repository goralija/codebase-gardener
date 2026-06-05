# GitHub App and API Specification

> Status: Ground truth
> Purpose: Define initial external product behavior and API expectations.

## Product surface

V1 is a GitHub App with a Gardener-hosted dashboard and hosted workers.

The backend API is implemented with Python, Django, Django REST Framework, and PostgreSQL. Long-running hosted work runs through Redis and Celery.

The product must support:

- GitHub App installation.
- Repository selection.
- Webhook ingestion.
- Hosted session execution.
- Branch and PR creation.
- PR comments and status reporting.
- Dashboard/API access for reports, settings, sessions, and billing.

## GitHub App events

V1 should handle:

- installation created/updated/deleted
- repository added/removed from installation
- push
- pull_request opened/synchronize/reopened/closed
- check_suite or workflow_run completion where available
- issue_comment or PR review events if needed for commands

## API principles

- Use versioned API routes.
- Use Django REST Framework serializers for API contracts.
- Keep JSON fields in `snake_case`.
- Scope every request to customer organization and repository where applicable.
- Enforce role permissions on the backend.
- Return predictable errors with code, message, and details.
- Expose reports, sessions, opportunities, constitution questions, settings, and billing data.
- Never expose repository secrets or raw code content unless there is a specific user-facing need and permission.
- Keep response shapes aligned with `docs/19-shared-json-contracts.md`.

## Core API resources

- organizations
- memberships
- github-installations
- managed-repositories
- logical-systems
- repository-constitutions
- constitution-questions
- analysis-snapshots
- entropy-scores
- gardening-sessions
- maintenance-opportunities
- maintenance-prs
- gardener-profiles
- subscriptions
- roi-estimates

## Worker behavior

Hosted workers must:

- run as Celery workers
- fetch the smallest repository data needed for the session
- respect GitHub installation permissions
- isolate customer data
- create branches with deterministic names
- avoid conflicting PRs in the same session
- persist analysis results and audit events
- fail safely and visibly

## Shared contracts

The first API implementation should expose fixture-backed responses matching `docs/19-shared-json-contracts.md` so the dashboard can be built before real analysis and session execution are complete.
