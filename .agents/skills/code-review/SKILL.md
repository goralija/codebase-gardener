---
name: code-review
description: Use when reviewing Codebase Gardener code, docs, skills, scoring logic, GitHub App behavior, worker behavior, autonomy policy, or AI-generated changes for correctness, safety, product fit, and tests.
---

# Code Review Skill

Use this skill for review before accepting changes.

## Required context

Read docs relevant to the changed area, especially:

1. `docs/00-product-vision.md`
2. `docs/09-autonomy-and-automation-rules.md`
3. `docs/11-security-and-compliance.md`
4. `docs/12-testing-strategy.md`
5. `docs/16-constitution-and-memory-schema.md`
6. `docs/17-entropy-signal-catalog.md`
7. `docs/18-technical-architecture.md`
8. `docs/19-shared-json-contracts.md`

## Review priorities

1. Product fit with autonomous codebase maintenance engineer direction.
2. PR/autonomy safety.
3. Correct source-truth and constitution handling.
4. Entropy score explainability and evidence.
5. Shared contract compatibility across lanes.
6. GitHub App permission and customer isolation.
7. Hosted worker reliability and failure visibility.
8. Tests and verification.
9. Documentation updates where product truth changed.
10. Simplicity and surgical changes.

## Checklist

- Does the change preserve GitHub App first positioning?
- Does it avoid dashboard-only behavior?
- Does it respect protected modules and never-touch paths?
- Does it ask on source-truth conflict?
- Can scoring output be traced to evidence?
- Are PRs blocked below confidence threshold?
- Are GitHub webhooks scoped and idempotent?
- Is raw source code stored only when necessary?
- Are sensitive changes audited?
- Are tests meaningful and relevant?

## Output format

Lead with findings ordered by severity. Include file and line references when possible. If no issues are found, say so and mention remaining risk or test gaps.
