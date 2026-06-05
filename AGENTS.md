# Codebase Gardener Agent Instructions

Codebase Gardener product truth lives in `docs/`.

Project-local agent skills live in `.agents/skills/<skill-name>/SKILL.md`.

When working in this repository:

- Read the relevant product docs before making product, architecture, API, storage, UI, automation, security, testing, deployment, or roadmap decisions.
- If your runtime auto-discovers project-local skills, use the matching skill normally.
- If your runtime does not auto-discover project-local skills, manually read the relevant `.agents/skills/<skill-name>/SKILL.md` file before acting.
- Use `.agents/skills/product-planning/SKILL.md` before changing product scope.
- Use `.agents/skills/backend-implementation/SKILL.md` for Django, DRF, PostgreSQL, Redis, and Celery work.
- Use `.agents/skills/github-app-implementation/SKILL.md` for GitHub App installation, webhook, permission, repository selection, branch, or PR execution work.
- Use `.agents/skills/frontend-implementation/SKILL.md` for React/Vite dashboard work.
- Use `.agents/skills/analysis-engine-implementation/SKILL.md` for Repowise wrapper, constitution, entropy, and fixture repo analysis work.
- Use `.agents/skills/repo-constitution-builder/SKILL.md` when working on `GARDENER.md`, constitution parsing, source-truth extraction, or onboarding questions.
- Use `.agents/skills/entropy-modeler/SKILL.md` when changing Repository Entropy Score behavior, thresholds, signals, or forecasts.
- Use `.agents/skills/gardening-session-planner/SKILL.md` when designing or implementing session triggers, lifecycle, ranking, reports, or hosted execution.
- Use `.agents/skills/safe-pr-author/SKILL.md` before implementing autonomous PR creation or maintenance changes.
- Use `.agents/skills/plan-next-step/SKILL.md` when choosing the next task from `docs/15-epics-and-tasks.md`.
- Use `.agents/skills/code-review/SKILL.md` when reviewing product, code, docs, skills, scoring, GitHub App, worker, autonomy, or AI-generated changes.
- Use `.agents/skills/testing/SKILL.md` before marking implementation, docs, skills, contracts, dashboard, GitHub App, worker, or PR safety work complete.
- Use `.agents/skills/documentation-update/SKILL.md` when product truth changes.
- Treat `docs/18-technical-architecture.md` and `docs/19-shared-json-contracts.md` as required context before cross-lane implementation work.
- Treat `docs/20-team-working-agreement.md` as required context before starting new feature branches or assigning lane work.
- Use short atomic feature branches from latest `main`; do not use long-lived lane branches for implementation.
- Treat `GARDENER.md` as the current repository constitution for this repo.
- Keep changes surgical and update docs only when product truth changes.

For Codex auto-discovery outside this repository, install/copy a skill folder to `${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>/SKILL.md` or another configured Codex skill root.
