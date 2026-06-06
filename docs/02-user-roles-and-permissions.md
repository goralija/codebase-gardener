# User Roles and Permissions

> Status: Ground truth
> Purpose: Define initial access rules for the GitHub App and Gardener dashboard.

## Organization and repository access

Gardener is installed as a GitHub App. Access starts from GitHub organization, repository, and team permissions, then narrows through Gardener roles.

Every action must be scoped to a customer organization and repository. Gardener-hosted workers must only access repositories granted by the GitHub App installation.

## Roles

- Owner: manages billing add-ons, installations, organization settings, and all repositories.
- Admin: configures repositories, schedules, autonomy policies, billing add-ons, and integrations.
- Maintainer: reviews reports, approves onboarding answers, and manages Gardener PR policy for assigned repositories.
- Reviewer: reviews reports and PRs but cannot change autonomy settings.
- Viewer: reads dashboards and reports only.
- Gardener Worker: service actor that scans repos, creates branches, opens PRs, posts comments, and writes approved memory/config updates.

## Permission principles

- Never rely only on frontend hiding.
- Require explicit permission for changing autonomy levels, protected modules, billing, schedules, or source-truth answers.
- Separate report visibility from the ability to open or merge PRs.
- Log sensitive configuration changes.
- Keep plan and price edits internal/staff-only until a payment provider exists.
- Gardener Worker must use the minimum GitHub permissions needed for the enabled features.

## Permission matrix

| Capability | Owner | Admin | Maintainer | Reviewer | Viewer | Gardener Worker |
| --- | --- | --- | --- | --- | --- | --- |
| Manage billing add-ons | Yes | Yes | No | No | No | No |
| View billing plan inputs | Yes | Yes | No | No | No | No |
| Install/remove repositories | Yes | Yes | No | No | No | No |
| View entropy reports | Yes | Yes | Yes | Yes | Yes | No |
| Edit repository constitution answers | Yes | Yes | Yes | No | No | Proposed only |
| Configure schedules/triggers | Yes | Yes | Yes | No | No | No |
| Configure autonomy policy | Yes | Yes | Yes | No | No | No |
| Open maintenance PRs | No | No | No | No | No | Yes, within policy |
| Auto-merge PRs | No default in v1 | No default in v1 | No default in v1 | No | No | No default in v1 |
| Update `.gardener/profile.yaml` | Yes | Yes | Yes | No | No | Proposed or PR only |

## Open implementation detail

The exact GitHub App permission scopes must be minimized during implementation and documented in `docs/10-integrations.md`.
