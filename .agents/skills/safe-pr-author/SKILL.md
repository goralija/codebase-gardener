---
name: safe-pr-author
description: Use when authoring, designing, reviewing, or implementing autonomous maintenance PR behavior, PR safety policy, risk tiers, confidence scoring, branch naming, PR bodies, or protected-path checks.
---

# Safe PR Author Skill

Use this skill before creating or changing Gardener PR behavior.

## Required context

Read these docs first:

1. `docs/09-autonomy-and-automation-rules.md`
2. `docs/16-constitution-and-memory-schema.md`
3. `docs/17-entropy-signal-catalog.md`
4. `docs/11-security-and-compliance.md`
5. `docs/12-testing-strategy.md`

## PR creation rules

- Create multiple focused PRs, not one mixed PR, unless the user explicitly requests a batch.
- Keep each PR small and coherent.
- Require confidence >= 85% by default for Tier 1 autonomous PRs.
- Use stricter evidence for dead-code removal.
- Never touch protected modules or never-touch paths.
- Do not auto-merge in the v1 default policy.
- Prefer draft PRs for assisted Tier 2 changes.

## PR body must include

- Goal.
- Triggering session.
- Risk tier.
- Confidence and reasons.
- Source evidence.
- Constitution rules used.
- Expected entropy impact.
- Changed paths.
- Tests/checks run or required.
- Rollback/revert guidance.

## Authoring workflow

1. Confirm the opportunity maps to an allowed fix tier.
2. Check the Repository Constitution and `.gardener/profile.yaml`.
3. Check protected paths and never-touch rules.
4. Verify the PR does not conflict with other session PRs.
5. Make the smallest change that satisfies the maintenance goal.
6. Run relevant tests/checks.
7. Write the explanatory PR body.
8. Record outcome hooks for learning.

## Stop conditions

Stop and produce a recommendation only if confidence is below threshold, protected code is involved, required tests cannot run, source truth conflicts, or the change touches business logic without explicit permission.
