# Entropy Signal Catalog

> Status: Draft reference
> Purpose: Preserve candidate entropy signals, weights, and thresholds for scoring work.

## Repository Entropy Score

Repository Entropy Score is a 0-100 score where higher means more degradation risk.

Component weights:

| Component | Weight |
| --- | --- |
| Architectural Entropy | 25% |
| Maintainability Entropy | 25% |
| Knowledge Entropy | 15% |
| Testing Entropy | 15% |
| Dependency Entropy | 10% |
| Operational Entropy | 10% |

Scores must be available at:

- repository level
- logical-system level
- module level
- file level

## Thresholds

Initial threshold categories:

- Healthy: low entropy, autonomy allowed within constitution.
- Warning: rising entropy, normal PR safety rules apply.
- Critical: high entropy, require tighter confidence and smaller PRs.
- No-autonomy: source truth, coverage, protected-module, or confidence conditions block PR creation.

Exact numeric thresholds are implementation details and should be validated against sample repositories.

## Architectural entropy signals

- dependency cycles
- layer violations
- boundary violations
- coupling growth
- blast radius growth
- central modules with rising churn
- monorepo logical-system leakage

V1 extraction uses Repowise health findings plus import cycles detected from the
Repowise knowledge graph.

## Maintainability entropy signals

- cyclomatic complexity
- deep nesting
- brain methods
- duplication
- dead code
- stale generated code
- code smells
- large files/modules with rising churn

## Knowledge entropy signals

- ownership concentration
- ownership dispersion in critical modules
- bus factor
- abandoned modules
- stale documentation
- missing ADRs or architecture docs
- repeated PR edits/rejections in same area

V1 extraction uses recent git history from the worker clone to detect low bus
factor and per-file ownership concentration.

## Testing entropy signals

- coverage gaps
- critical paths without tests
- flaky tests
- missing regression tests around hotspots
- tests not changing with risky modules
- CI failures tied to test instability

## Dependency entropy signals

- outdated packages
- abandoned packages
- dependency graph sprawl
- dependency patch opportunities
- lockfile drift
- known advisories when available from light security sources

V1 extraction detects dependency manifests without nearby lockfiles and
dependency/package-related Repowise health findings.

## Operational entropy signals

- CI failure frequency
- repeated reverts
- unstable release or deployment signals if available
- long-running checks
- failed Gardener sessions
- PRs blocked by unclear source truth

V1 extraction detects missing CI configuration, CI configurations that do not
appear to run tests, and CI/pipeline-related Repowise health findings.

## Forecast rules

Forecasts should explain expected future movement and confidence. They should use trend data when available and degrade to lower-confidence current-state warnings when history is insufficient.

## ROI signals

Acceptable ROI claims:

- engineering hours saved
- hotspots removed before incidents
- cleaner and more maintainable codebase
- entropy reduced
- focused PRs merged

Avoid precise monetary claims unless the customer has configured hourly cost assumptions.
