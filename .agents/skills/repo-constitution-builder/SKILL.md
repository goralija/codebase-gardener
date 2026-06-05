---
name: repo-constitution-builder
description: Use when building, parsing, updating, validating, or designing Repository Constitution behavior, source-truth discovery, `GARDENER.md`, `.gardener/profile.yaml`, onboarding questions, or conflict handling.
---

# Repository Constitution Builder Skill

Use this skill whenever work touches deterministic project source truth.

## Required context

Read these docs first:

1. `docs/16-constitution-and-memory-schema.md`
2. `docs/09-autonomy-and-automation-rules.md`
3. `docs/01-product-domain.md`
4. `docs/11-security-and-compliance.md`

Read `GARDENER.md` for this repository's own constitution.

## Core rules

- Build the Repository Constitution from source-truth files and onboarding answers.
- Prefer asking over silently resolving conflicting source truth.
- Treat inferred code behavior as evidence, not as higher authority than docs.
- If docs say a boundary exists and code violates it, record a violation.
- Memory in `.gardener/profile.yaml` can influence ranking, but never overrides explicit constitution rules.
- Keep the constitution auditable: every rule should have evidence or an explicit user answer.

## Source-truth discovery workflow

1. Search for standard files: `GARDENER.md`, README, architecture docs, ADRs, `AGENTS.md`, `CLAUDE.md`, `.agents/**`, `.claude/**`, contribution docs, code owners, workspace files, CI config, and test config.
2. Extract candidate rules for protected modules, allowed fixes, architecture boundaries, ownership, domains, test rules, ignored paths, and risk policies.
3. Attach evidence to each candidate rule.
4. Detect conflicts and missing critical categories.
5. Create ConstitutionQuestions instead of guessing.
6. Build or update normalized constitution output.

## Validation checklist

- Protected modules are explicit.
- Never-touch paths are explicit.
- Autonomous, assisted, and advisory-only fixes are separated.
- Architecture boundaries are machine-checkable where practical.
- Ignored paths include generated/vendor/migration-like areas.
- Test rules exist for critical paths.
- Completeness score reflects missing categories.
- Conflicts are surfaced to the user.

## Stop conditions

Stop and ask if two source-truth files conflict on a protected module, architecture boundary, allowed autonomy level, or never-touch path.
