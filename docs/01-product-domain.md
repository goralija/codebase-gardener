# Product Domain

> Status: Ground truth
> Purpose: Define the problem space Codebase Gardener models.

Codebase Gardener operates in the domain of codebase degradation prevention. The core assumption is that active repositories decay when many humans and agents add features without a continuous maintenance loop.

## Domain layers

### Repository source truth

Gardener must discover repository intent from standard files before acting:

- `GARDENER.md`
- `README.md`
- `ARCHITECTURE.md`
- ADR folders such as `docs/adr/` or `architecture/adr/`
- `AGENTS.md`
- `CLAUDE.md`
- `.agents/**`
- `.claude/**`
- other agent, architecture, policy, and contribution files found by deterministic file search

When source truth is incomplete or conflicting, Gardener asks onboarding questions and runs conservatively.

### Repository intelligence

Gardener uses a Repowise fork and additional scanners to understand:

- dependency graph
- import boundaries
- git history
- churn
- ownership
- hotspots
- dead code
- module structure
- documentation freshness
- light security and dependency risk

### Entropy and degradation

Degradation includes:

- architectural entropy: cycles, layer violations, coupling growth, blast radius
- maintainability entropy: complexity, duplication, dead code, code smells
- knowledge entropy: ownership concentration, bus factor, abandoned modules, stale docs
- testing entropy: coverage gaps, critical paths without tests, flaky tests
- dependency entropy: outdated or risky packages, dependency sprawl
- operational entropy: CI failures, release instability, repeated reversions

### Autonomous maintenance

Gardener turns diagnosis into maintenance work:

- rank opportunities by impact, risk, effort, and confidence
- create focused PRs that do not interfere with each other
- explain each PR with evidence, expected entropy effect, and safety reasoning
- learn from outcomes and update repo/team memory

## Main concepts

- Repository: a GitHub repository managed by Gardener.
- Managed Repository: a repository selected and billed for ongoing Gardener sessions.
- Logical System: a subsystem inside a repo or monorepo, such as frontend, backend, platform, shared packages, or mobile.
- Repository Constitution: the deterministic source-truth model Gardener uses to decide what matters and what it may touch.
- Gardener Profile: learned repo/team preferences in `.gardener/profile.yaml`.
- Gardening Session: one hosted run that observes, diagnoses, forecasts, plans, executes, and learns.
- Maintenance Opportunity: a candidate action that may reduce entropy or prevent degradation.
- Focused Maintenance PR: a small PR created for one coherent maintenance outcome.

## MVP domain boundary

V1 must cover GitHub App onboarding, repository scanning, constitution building, entropy reports, architecture violations, session planning, focused maintenance PRs, and learning memory. Full enterprise security, generic project management, and broad deployment orchestration are outside the initial boundary.
