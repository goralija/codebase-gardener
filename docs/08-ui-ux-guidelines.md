# UI/UX Guidelines

> Status: Ground truth
> Purpose: Define the product experience for the GitHub App dashboard.

## Design principles

- Build a work-focused engineering operations tool, not a marketing page.
- Use React, Vite, TypeScript, TanStack Query, TanStack Router, shadcn/ui preset `bLToCnFy`, Lucide Icons, Valibot, and TanStack Form.
- Optimize for scanability, confidence, and fast review.
- Show evidence before recommendations.
- Make autonomy settings and protected boundaries obvious.
- Do not bury unanswered constitution questions.
- Keep PR creation explainable and reversible.

## First screen

After onboarding, the first useful screen should show:

- Repository Entropy Score and trend.
- Top entropy contributors.
- Architecture violations.
- Open constitution questions.
- Active or recent gardening sessions.
- Maintenance PRs and outcomes.
- ROI summary.

## Navigation

Core navigation should include:

- Repositories
- Entropy
- Constitution
- Sessions
- Opportunities
- Pull Requests
- ROI
- Settings

## Page patterns

### Repository report

Show repo-level score first, then logical systems, modules, and files. Always include component breakdown and evidence.

### Constitution

Show source-truth coverage, conflicts, unanswered questions, protected modules, allowed fixes, and ignored paths.

### Sessions

Show lifecycle phase, trigger, duration, outputs, failures, and generated PRs.

### PR review support

Show goal, evidence, confidence, risk tier, expected entropy delta, affected paths, tests/checks, and rollback/revert guidance.

### Fixture-first development

Build first-report and session screens against `fixtures/contracts/` data that matches `docs/19-shared-json-contracts.md` before real backend integration is ready.

### Settings

Use explicit controls for triggers, autonomy mode, protected areas, PR frequency, and allowed fix tiers.

## States

Every important screen must handle:

- loading
- empty
- first-run
- partial scan
- permission denied
- conflicting source truth
- session failed
- PR blocked by policy

## Language

Use product language like `entropy`, `constitution`, `maintenance opportunity`, `focused PR`, and `confidence`. Avoid raw internal metric names unless the user opens details.
