# Autonomy and Automation Rules

> Status: Ground truth
> Purpose: Define Gardener autonomy boundaries, maintenance tiers, and PR safety rules.

Gardener must be autonomous enough to be useful, but deterministic enough to earn trust. Full autonomy in v1 means hosted sessions can run and create maintenance PRs. It does not mean Gardener may rewrite critical business logic or merge risky changes without review.

## Session lifecycle

Every Gardening Session follows:

1. Observe
2. Diagnose
3. Forecast
4. Plan
5. Execute
6. Learn

## Autonomy modes

- Conservative: reports and recommendations only.
- Assisted: reports plus draft PRs.
- Autonomous: reports plus focused PRs within allowed tiers and confidence policy.
- Aggressive: multiple scheduled PRs and broader action surface. This is not a v1 default.

## Fix tiers

### Tier 1 - Autonomous

Confirmed v1 autonomous categories:

- documentation updates
- lint/format-only changes
- generated artifact refreshes
- dependency patch updates with passing checks
- dead-code removal only at very high confidence

### Tier 2 - Assisted

Gardener may create draft PRs or recommendations:

- test generation
- refactoring
- module extraction
- complexity reduction
- layer violation repair
- dependency minor or major upgrades

### Tier 3 - Advisory

Gardener must not directly modify these by default:

- auth
- payments
- pricing
- permissions
- business workflows
- migrations
- security-sensitive code
- customer-defined protected modules

## Confidence policy

- Creating any PR requires confidence >= 90 percent unless the Repository Constitution sets a stricter threshold.
- Dead-code removal should require stronger evidence than ordinary Tier 1 work.
- Confidence must be explained in the PR body.
- If confidence is below threshold, create a recommendation only.

## PR rules

- If an organization's autonomous PR add-on is disabled, sessions may still create visible blocked PR plans and recommendations, but workers must not create GitHub PRs.
- Prefer multiple focused PRs that do not interfere with one another.
- Do not mix unrelated maintenance categories in one PR.
- Include evidence, risk tier, confidence, expected entropy impact, changed paths, and verification.
- Do not auto-merge in the v1 default policy.
- If a session produces conflicting PR candidates, rank them and defer lower-priority work.

## Autonomous authoring scope

- Docs maintenance fixes use a deterministic author; other categories (dead-code, complexity, refactoring, layer violations, tests) are authored by an LLM (OpenRouter) that produces a minimal, validated edit.
- AI edits are validated before a PR is opened (syntax/AST parse and a bounded-change guard); a failed validation fails the plan and creates no PR.
- A session approves and executes tier_1 autonomous plans that have an implemented file fix, up to its per-session cap; PRs are labeled by risk tier and confidence; no auto-merge.
- The user is notified on session completion with the authored PRs and their risk tiers.

## Learning rules

- Track accepted, rejected, edited, merged, reverted, and failed PRs.
- Write learned preferences to `.gardener/profile.yaml`.
- Learned preferences never override explicit Repository Constitution rules.
