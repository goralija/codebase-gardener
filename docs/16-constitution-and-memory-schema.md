# Constitution and Memory Schema

> Status: Ground truth
> Purpose: Define the customer repository files Gardener reads and writes.

## `GARDENER.md`

`GARDENER.md` is the human-readable Repository Constitution. It is the preferred customer-editable source truth for Gardener.

If a first scan cannot find `GARDENER.md`, Gardener should keep the repository in `no_autonomy` and may open a draft PR that adds a conservative starter constitution. That generated file is only a proposal; merging or editing it is the customer approval step that turns it into source truth.

Recommended sections:

- Product or repository purpose.
- Architecture boundaries.
- Protected modules.
- Never-touch paths.
- Autonomous fixes allowed.
- Assisted-only fixes.
- Advisory-only areas.
- Test rules.
- Ownership and reviewer rules.
- Ignored paths.
- Health priorities.
- Security-sensitive areas.
- Trigger and PR preferences.

## Constitution normalized model

Gardener should normalize source truth into:

- protected_modules: names and paths
- never_touch: glob patterns and reasons
- autonomous_fixes_allowed: categories and constraints
- assisted_fixes_allowed: categories and constraints
- advisory_only: categories and paths
- architecture_boundaries: allowed and forbidden imports/dependencies
- ownership: owners, reviewers, teams, bus-factor hints
- domains: business/domain module definitions
- test_rules: required tests by area
- ignored_paths: generated, vendor, migrations, snapshots, fixtures
- risk_policies: confidence thresholds and special handling
- evidence: source file, section, line or excerpt reference
- completeness: score and missing categories

## Source-truth discovery

Gardener should search for:

- `GARDENER.md`
- `README.md`
- `ARCHITECTURE.md`
- ADR directories
- `AGENTS.md`
- `CLAUDE.md`
- `.agents/**`
- `.claude/**`
- contributing docs
- code owners files
- package/workspace files
- CI and test configuration

No single file besides `GARDENER.md` is assumed to be complete. The Constitution Builder combines evidence and asks when important details conflict.

## Conflict handling

If source-truth files conflict, Gardener should ask rather than silently decide.

Example:

- `ARCHITECTURE.md` says UI must not import database code.
- Observed code imports database from UI.
- Gardener records an architecture violation, not a new rule.

## `.gardener/profile.yaml`

`.gardener/profile.yaml` stores learned repo/team memory.

Suggested fields:

```yaml
version: 1
repository:
  preferred_pr_size: small
  preferred_pr_categories:
    accepted: []
    rejected: []
  protected_patterns_learned: []
  review_preferences: []
outcomes:
  accepted_categories: {}
  rejected_categories: {}
  reverted_categories: {}
notes:
  - source: "pr-outcome"
    text: "Team usually accepts dependency patch PRs."
```

## Memory rules

- Memory can influence ranking and presentation.
- Memory can reduce future PR frequency for rejected categories.
- Memory can suggest constitution updates.
- Memory never overrides explicit constitution rules.
- Memory updates should be auditable and preferably proposed through PRs.
