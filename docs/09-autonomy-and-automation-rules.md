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

First scans are baseline-only. They run repository analysis, store and promote
the initial baseline, and may propose a starter `GARDENER.md`, but they do not
create maintenance PR plans. If any hosted session analysis finds that
`GARDENER.md` is missing, Gardener may propose the same starter constitution PR.
If a manual or automated session runs before any baseline exists, it promotes
the current analysis and stops without maintenance PRs.

A later non-first-scan session compares current analysis against the latest
promoted baseline. Automated triggers plan only from new or worsened drift.
Manual triggers first use drift-relevant opportunities; if no drift-relevant
opportunities exist, they may plan from current maintenance opportunities not
already covered by an active unblocked Gardener PR plan. All PR creation still
requires repository autonomy, add-on, constitution, protected-path, confidence,
and implemented-fix gates.

Every completed non-first-scan session promotes its current analysis as the
latest relevant baseline. After all Gardener-authored PRs from that session are
merged or closed, Gardener runs one idempotent post-PR refresh analysis and
promotes it too. Reverts of merged Gardener PRs also trigger a refresh because
the default branch changed again.

## Autonomy modes

- Conservative: reports and recommendations only.
- Assisted: reports plus draft PRs.
- Autonomous: reports plus focused PRs within allowed tiers and confidence policy.
- Aggressive: multiple scheduled PRs and broader action surface. This is not a v1 default.

New repositories default to Conservative. Manual sessions are enabled by
default; scheduled, commit-count, risky-module, PR-opened, and CI-failure
triggers are disabled until the user enables them.

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
- For drift-aware sessions, PR body evidence must include the baseline commit, current commit, and why the opportunity is new or worse since the baseline.
- Do not auto-merge in the v1 default policy.
- If a session produces conflicting PR candidates, rank them and defer lower-priority work.

## Autonomous authoring scope

- Docs maintenance fixes use a deterministic author; other categories (dead-code, complexity, refactoring, layer violations, tests) are authored by an LLM (OpenRouter) that produces a minimal, validated edit.
- AI edits are validated before a PR is opened (syntax/AST parse and a bounded-change guard); oversized files are chunked and analyzed with bounded parallel workers, and a failed validation fails the plan and creates no PR.
- A session approves and executes tier_1 autonomous plans that have an implemented file fix, up to its per-session cap; PRs are labeled by risk tier and confidence; no auto-merge.
- Failed CI on a Gardener-authored PR may trigger one AI repair attempt on the same branch when the original plan is still eligible, the autonomous PR add-on is enabled, and the plan category/path is supported by the AI author. Repair commits include failed-check context and never auto-merge the PR.
- The user is notified on session completion with the authored PRs and their risk tiers.

## Learning rules

- Track accepted, rejected, edited, merged, reverted, and failed PRs.
- Track terminal PR outcomes on each `MaintenancePRPlan` with append-only outcome history.
- Write learned preferences to `.gardener/profile.yaml`.
- Learned preferences never override explicit Repository Constitution rules.

Trigger rules use the latest promoted baseline constitution. Commit counters
reset when a session promotes a new baseline because the current default branch
state has been observed.
