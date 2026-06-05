# Feature Map

> Status: Ground truth
> Purpose: Define product modules and v1 scope.

## V1 modules

### GitHub App onboarding

- Install GitHub App.
- Select repositories.
- Detect monorepo logical systems.
- Run first scan.
- Build draft Repository Constitution.
- Ask onboarding questions for missing or conflicting source truth.

### Repository Constitution

- Search for standard source-truth files.
- Parse `GARDENER.md`, README, architecture docs, ADRs, agent docs, and inferred code evidence.
- Normalize protected modules, allowed fixes, architecture boundaries, ownership, domains, test rules, ignored paths, and risk policies.
- Track Constitution Completeness Score.

### Repository intelligence

- Fork and use Repowise as the foundation.
- Build graph, git, ownership, hotspot, dead-code, documentation, decision, and code-health intelligence.
- Add light security/dependency maintenance signals.
- Support all languages and ecosystems as a product goal, with capability tiers when parser coverage differs.

### Entropy reports

- Compute Repository Entropy Score.
- Break down architecture, maintainability, knowledge, testing, dependency, and operational entropy.
- Show repo, logical-system, module, and file-level scores.
- Include trend and forecast, not only current score.

### Gardening sessions

- Support manual, schedule, after N commits, risky module changes, PR opened, and CI failure triggers.
- Run on Gardener-hosted workers.
- Execute observe, diagnose, forecast, plan, execute, and learn lifecycle.
- Create multiple focused PRs that do not interfere with one another.

### Maintenance PRs

- Open low-risk autonomous PRs.
- Create draft PRs for medium-risk assisted changes.
- Never touch protected high-risk areas by default.
- Include evidence, confidence, expected entropy impact, and verification.

### Learning and memory

- Track accepted, rejected, edited, merged, reverted, and failed PRs.
- Store repo/team memory in `.gardener/profile.yaml`.
- Let memory influence ranking and proposal style, but never override explicit constitution rules.

### Dashboard and ROI

- Show first-run report with entropy, maintenance PRs, and architecture violations.
- Show ROI estimates such as engineering hours saved, hotspots removed before incidents, and maintainability improvements.
- Show session history and PR outcome learning.

## Later features

- Deeper Snyk-style security integrations.
- Enterprise self-hosted/local hosted version for large customers that demand it.
- Auto-merge policies after stronger evidence and explicit customer approval.
- Broader provider support beyond GitHub.

## Deferred or excluded emphasis

- Making codebases perfect automatically.
- Large risky rewrites.
- Standalone dashboard-only positioning.
- Full enterprise compliance before the GitHub App product proves value.
