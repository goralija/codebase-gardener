---
name: frontend-implementation
description: Use when implementing Codebase Gardener frontend work in React, Vite, TypeScript, TanStack Query, TanStack Router, shadcn/ui, Lucide Icons, Valibot, TanStack Form, Vitest, or Playwright.
---

# Frontend Implementation Skill

Use this skill for Lane A dashboard and UI work.

## Required context

Read these docs first:

1. `docs/18-technical-architecture.md`
2. `docs/19-shared-json-contracts.md`
3. `docs/05-user-flows.md`
4. `docs/08-ui-ux-guidelines.md`
5. `docs/12-testing-strategy.md`

## Stack rules

- Use React, Vite, TypeScript, TanStack Query, TanStack Router, shadcn/ui, Lucide Icons, Valibot, TanStack Form, Vitest, and Playwright.
- Build dashboard/product screens, not marketing pages.
- Start with fixture data matching `docs/19-shared-json-contracts.md` when backend integration is not ready.
- Move from fixtures to DRF API responses without changing the screen contract.

## UX rules

- Make entropy, constitution questions, architecture violations, sessions, opportunities, PR plans, and ROI scannable.
- Show evidence and confidence before recommending or displaying automation.
- Handle loading, empty, error, permission-denied, first-run, and partial-report states.
- Use Lucide icons for actions and status indicators when helpful.
- Use Valibot and TanStack Form for settings/question forms.

## Workflow

1. Identify the user flow and contract being displayed or edited.
2. Build against fixture JSON when real API is not ready.
3. Add typed data mapping.
4. Implement UI states and validation.
5. Add Vitest coverage for data mapping/components.
6. Add Playwright coverage for meaningful user flows.
7. Update docs if UI product behavior changes.

## Done criteria

- UI consumes the shared contract or matching API response.
- Vitest/Playwright coverage exists where relevant.
- No visible text overflows or ambiguous automation states.
