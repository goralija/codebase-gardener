---
name: documentation-update
description: Use after Codebase Gardener implementation or planning work when product truth, architecture, GitHub App behavior, constitution rules, entropy scoring, autonomy policy, integrations, security, testing, deployment, roadmap, or backlog scope changes.
---

# Documentation Update Skill

Use this skill when docs need to change.

## Rule

Update docs when work changes product truth. Do not update docs for implementation-only changes that do not change decisions, behavior, or conventions.

## Docs map

- Vision or positioning: `docs/00-product-vision.md`
- Product domain and concepts: `docs/01-product-domain.md`
- Roles and permissions: `docs/02-user-roles-and-permissions.md`
- Entities and relationships: `docs/03-system-model.md`
- Modules and scope: `docs/04-feature-map.md`
- Workflows: `docs/05-user-flows.md`
- GitHub App/API behavior: `docs/06-github-app-api-spec.md`
- Data and storage: `docs/07-data-storage-rules.md`
- UI patterns: `docs/08-ui-ux-guidelines.md`
- Autonomy and PR safety: `docs/09-autonomy-and-automation-rules.md`
- Integrations: `docs/10-integrations.md`
- Security and compliance: `docs/11-security-and-compliance.md`
- Testing: `docs/12-testing-strategy.md`
- Deployment: `docs/13-deployment-and-environments.md`
- Roadmap: `docs/14-roadmap.md`
- Backlog: `docs/15-epics-and-tasks.md`
- Constitution and memory schema: `docs/16-constitution-and-memory-schema.md`
- Entropy signals and scoring: `docs/17-entropy-signal-catalog.md`
- Technical architecture and lanes: `docs/18-technical-architecture.md`
- Shared JSON contracts: `docs/19-shared-json-contracts.md`

## Workflow

1. Identify what product truth changed.
2. Update only relevant docs.
3. Keep docs decisive and specific.
4. Remove stale or contradictory guidance.
5. Preserve open details only when they genuinely remain unresolved.
6. Update project-local skills if the workflow agents should follow changed rules.

## Done criteria

- Docs match accepted decisions or implemented behavior.
- No TODO placeholders remain.
- Updated docs do not contradict `GARDENER.md` or founder answers without an explicit note.
