# Data and Storage Rules

> Status: Ground truth
> Purpose: Define persistence, tenancy, and data modeling rules.

## Storage principles

- Store customer organization, repository, session, score, opportunity, PR, billing, and audit data centrally in Gardener-hosted infrastructure.
- Use PostgreSQL as the primary database.
- Use Django models and migrations for product/session data.
- Store learned repo/team memory in the customer repository at `.gardener/profile.yaml`.
- Store human-readable repository constitution in the customer repository at `GARDENER.md`.
- Keep raw source code storage minimal. Prefer derived signals, hashes, paths, metrics, and evidence references.
- Encrypt credentials and installation tokens.
- Separate customer data by organization and repository.

## Repository-side files

`GARDENER.md` is the human source truth for repository maintenance rules.

`.gardener/profile.yaml` stores learned preferences, such as accepted PR categories, rejected patterns, protected modules learned from human behavior, and review preferences.

Gardener may propose updates to these files through PRs. Direct writes require explicit future policy.

## Analysis snapshots

Snapshots should be immutable enough to support trend analysis. A new snapshot should record:

- commit SHA
- timestamp
- trigger
- repository and logical-system scope
- signal versions
- entropy score breakdown
- relevant constitution version
- generated opportunities and forecasts

## Migrations and schema changes

- Use explicit Django migrations.
- Keep audit records for sensitive configuration and billing changes.
- Avoid destructive data changes without a migration plan.
- Index common lookup dimensions: organization, repository, session, commit SHA, score scope, PR outcome, and trigger.

## Reporting data

Reporting should support:

- entropy trends
- score breakdowns
- system/module/file drill-down
- PR outcomes
- ROI estimates
- Constitution Completeness Score
- session durations and failures
