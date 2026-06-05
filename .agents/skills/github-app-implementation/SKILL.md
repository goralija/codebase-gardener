---
name: github-app-implementation
description: Use when implementing or designing Codebase Gardener GitHub App behavior, webhooks, installation flow, repository selection, branch/PR creation, GitHub permissions, status checks, or hosted worker integration.
---

# GitHub App Implementation Skill

Use this skill for the v1 product surface.

## Required context

Read these docs first:

1. `docs/06-github-app-api-spec.md`
2. `docs/10-integrations.md`
3. `docs/11-security-and-compliance.md`
4. `docs/13-deployment-and-environments.md`
5. `docs/18-technical-architecture.md`
6. `docs/19-shared-json-contracts.md`
7. `docs/12-testing-strategy.md`

Read `docs/09-autonomy-and-automation-rules.md` for PR behavior.

## Mandatory rules

- Treat GitHub App first as a protected product decision.
- Use Django/DRF for API behavior and Celery for long-running hosted work.
- Use GitHub REST through Python HTTP clients.
- Minimize GitHub permissions.
- Verify webhook signatures.
- Make webhook handling idempotent.
- Scope all data to customer organization, installation, and repository.
- Do not create branches or PRs unless repository policy allows it.
- Persist failures visibly.
- Audit sensitive settings and worker actions.

## Implementation workflow

1. Identify GitHub event or API action.
2. Check installation/repository/customer scope.
3. Check role and autonomy policy.
4. Implement idempotent processing.
5. Use hosted worker path for long-running analysis.
6. Add tests for permissions, event replay, failure handling, and API rate-limit behavior.
7. Update docs if scopes, events, or product behavior changes.

## Avoid

- Broad OAuth scopes when GitHub App installation permissions are enough.
- Direct writes outside branch/PR/comment/status surfaces.
- Silent webhook failures.
- Storing raw code unnecessarily.
- Mixing GitHub provider assumptions into generic domain logic.

## Done criteria

- Webhook/API path is tested.
- GitHub permission need is documented.
- Customer isolation is verified.
- Errors are visible without leaking secrets or code.
