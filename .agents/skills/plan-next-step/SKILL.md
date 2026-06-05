---
name: plan-next-step
description: Use when an agent needs to choose the next Codebase Gardener backlog task from docs/15-epics-and-tasks.md, gather task-relevant docs, and produce a clarification-aware implementation plan before coding.
---

# Plan Next Step Skill

Use this skill to decide what Codebase Gardener task should be planned next. This skill is for planning until the user asks for implementation.

## Core rule

Do not load all docs into context. Extract the selected task, its dependencies, lane, and the smallest relevant doc sections needed to plan safely.

## Step 1: Select the next task

1. Inspect task headings:

   ```bash
   rg -n "^#### E[0-9]{2}-T[0-9]{2}" docs/15-epics-and-tasks.md
   ```

2. For each candidate in order, extract only that task block and direct dependencies.
3. Choose the first task whose status is `Open`, dependencies are satisfied or `None`, lane is appropriate for the current engineer/agent, and acceptance criteria are not already satisfied by repo evidence.
4. If the task is blocked by an unresolved open question, report the blocker instead of planning implementation.

## Step 2: Extract minimal task context

Capture:

- task ID and title
- status
- phase
- lane
- complexity
- intent
- dependencies
- acceptance criteria
- verification
- parent epic outcome

## Step 3: Read relevant docs

Use this guide:

- Product/scope: `docs/00-product-vision.md`, `docs/04-feature-map.md`, `docs/14-roadmap.md`
- Architecture/lane contracts: `docs/18-technical-architecture.md`, `docs/19-shared-json-contracts.md`
- Constitution: `docs/16-constitution-and-memory-schema.md`, `docs/09-autonomy-and-automation-rules.md`
- Entropy: `docs/17-entropy-signal-catalog.md`
- GitHub App/API: `docs/06-github-app-api-spec.md`, `docs/10-integrations.md`, `docs/11-security-and-compliance.md`
- Sessions/PRs: `docs/05-user-flows.md`, `docs/09-autonomy-and-automation-rules.md`
- Data/storage: `docs/03-system-model.md`, `docs/07-data-storage-rules.md`
- Deployment/workers: `docs/13-deployment-and-environments.md`
- UI/dashboard: `docs/08-ui-ux-guidelines.md`
- Testing: `docs/12-testing-strategy.md`

## Output format

```md
## Selected task

## Lane

## Why this task is next

## Relevant docs read

## Implementation plan

## Acceptance criteria

## Verification

## Open questions / blockers
```

## Stop conditions

Stop and ask if task selection depends on unanswered PR safety questions, a missing shared contract, or a conflict between docs and `GARDENER.md`.
