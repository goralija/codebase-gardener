---
name: backend-implementation
description: Use when implementing Codebase Gardener backend work in Python, Django, Django REST Framework, PostgreSQL, Redis, Celery, GitHub REST integration, APIs, serializers, models, migrations, or hosted worker plumbing.
---

# Backend Implementation Skill

Use this skill for Lane A backend work and any Django/DRF/Celery implementation.

## Required context

Read these docs first:

1. `docs/18-technical-architecture.md`
2. `docs/19-shared-json-contracts.md`
3. `docs/03-system-model.md`
4. `docs/06-github-app-api-spec.md`
5. `docs/07-data-storage-rules.md`
6. `docs/11-security-and-compliance.md`
7. `docs/12-testing-strategy.md`

## Stack rules

- Use Python, Django, Django REST Framework, PostgreSQL, Redis, and Celery.
- Use Django models and migrations for product/session data.
- Use DRF serializers for API contracts.
- Keep API JSON fields in `snake_case`.
- Use GitHub REST through Python HTTP clients.
- Use Celery for hosted session jobs, background work, and scheduled work.

## Mandatory rules

- Scope every object to customer organization/repository where applicable.
- Verify GitHub webhook signatures.
- Keep webhook handling idempotent.
- Encrypt or protect installation tokens and secrets.
- Do not store raw source code unless a feature explicitly requires it.
- Keep serializer output aligned with `docs/19-shared-json-contracts.md`.
- Add audit events for sensitive settings and worker actions.

## Workflow

1. Identify the lane and backlog task.
2. Read the relevant JSON contract.
3. Implement model, serializer, API, Celery task, or GitHub integration behavior.
4. Add permission, organization, and repository scoping.
5. Add pytest coverage.
6. Update docs if product truth or contract shape changes.

## Done criteria

- pytest passes for the changed backend area.
- Migrations exist for schema changes.
- API output matches the shared contract.
- Webhook and token paths are secure when touched.
