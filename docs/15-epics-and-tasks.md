# Epics and Tasks

> Status: Ground truth
> Purpose: Parallel implementation backlog for a three-person team.

## Backlog conventions

- Task IDs are stable and use `E##-T##`.
- Status is `Open` until implementation evidence satisfies acceptance criteria.
- Phases are `MVP`, `V1 Hardening`, or `Future`.
- Lane is `Shared`, `Lane A`, `Lane B`, or `Lane C`.
- Complexity is `S`, `M`, `L`, or `XL`.
- Dependencies use task IDs or `None`.
- Acceptance criteria describe externally observable completion.
- Verification describes tests, checks, reviews, or documentation validation.

## Product constraints

- V1 is a sellable GitHub App experience.
- V1 uses Django, Django REST Framework, PostgreSQL, Redis, Celery, React/Vite, TypeScript, TanStack Query/Router, shadcn/ui, Lucide Icons, Valibot, TanStack Form, pytest, Playwright, and Vitest.
- V1 uses Gardener-hosted workers.
- V1 must support monorepos.
- V1 includes full autonomy for safe PR creation, not risky auto-rewrites.
- V1 uses `GARDENER.md` for repository constitution and `.gardener/profile.yaml` for learned memory.
- V1 includes light security maintenance but is not a full security platform.

## Three-lane split

- Lane A - Platform, GitHub App, API, Dashboard.
- Lane B - Repository Intelligence, Constitution, Entropy.
- Lane C - Sessions, PR Automation, Learning.

The lanes should work through shared JSON contracts in `docs/19-shared-json-contracts.md`. Each lane should build fixtures/mocks for other lanes' outputs before real integration is ready.

## E00 Shared Foundation and Contracts

### Outcome

The team has agreed stack, repo scaffold, fixtures, and shared JSON contracts so all three lanes can work independently.

#### E00-T01 Lock stack and architecture docs

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: S
- Intent: Record the selected Django/DRF/Celery/React/Repowise stack and three-lane execution model.
- Dependencies: None
- Acceptance criteria: Technical architecture docs and backlog name the stack and lanes explicitly.
- Verification: `docs/18-technical-architecture.md`, `docs/19-shared-json-contracts.md`, and this backlog are updated.

#### E00-T02 Scaffold repository structure

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: M
- Intent: Create the initial `backend/`, `analysis_engine/`, `frontend/`, and `fixtures/` directories with minimal runnable projects.
- Dependencies: E00-T01
- Acceptance criteria: Django project boots, frontend dev server boots, analysis package imports, and fixture directory exists.
- Verification: `make backend-check`, `make backend-test`, `make analysis-test`, `make frontend-build`, and Playwright smoke pass.

#### E00-T03 Implement shared contract fixtures

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: M
- Intent: Add JSON fixtures matching every contract in `docs/19-shared-json-contracts.md`.
- Dependencies: E00-T01
- Acceptance criteria: Fixture files exist for RepositoryConstitution, GardenerProfile, AnalysisSnapshot, EntropyReport, MaintenanceOpportunity, GardeningSessionResult, MaintenancePRPlan, and FirstReportFixture.
- Verification: `make fixtures-validate` validates JSON Schema-backed fixtures and frontend imports `first_report_fixture.json`.

#### E00-T04 Establish CI and test commands

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: M
- Intent: Define local and CI commands for pytest, Vitest, Playwright, linting, and docs/skill validation.
- Dependencies: E00-T02
- Acceptance criteria: A single documented command set verifies backend, frontend, analysis, docs, and skills.
- Verification: Root `make check` and `.github/workflows/checks.yml` run fixture validation, docs/skills validation, backend checks/tests, analysis tests, frontend lint/Vitest/build, and Playwright smoke. `make runtime-check` verifies local services and migrations.

## E01 Product Foundation and Safety Decisions

### Outcome

Product truth and unresolved autonomy assumptions are clear before implementation hardens behavior.

#### E01-T01 Create product docs and local skills

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: M
- Intent: Establish docs, AGENTS instructions, and project-local skills from clarified product answers.
- Dependencies: None
- Acceptance criteria: `docs/`, `AGENTS.md`, `GARDENER.md`, and `.agents/skills/` exist and reflect founder answers.
- Verification: Skill validation passes and docs have no placeholder TODOs.

#### E01-T02 Resolve PR safety open questions

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: S
- Intent: Confirm unanswered autonomy questions 25-29 and update safety docs.
- Dependencies: E01-T01
- Acceptance criteria: Tier 1, Tier 2, never-touch areas, PR confidence threshold, and auto-merge policy are explicitly confirmed.
- Verification: `docs/09-autonomy-and-automation-rules.md` has no unanswered assumption block.

## E02 Lane A - Platform, GitHub App, API, Dashboard

### Outcome

Customers can install the GitHub App, select repositories, and view reports from real or fixture data.

#### E02-T01 Build Django/DRF product foundation

- Status: Done
- Phase: MVP
- Lane: Lane A
- Complexity: L
- Intent: Implement the backend foundation with Django, DRF, PostgreSQL settings, core apps, and standard API conventions.
- Dependencies: E00-T02, E00-T03
- Acceptance criteria: Backend exposes versioned API routes and can serve fixture-backed report data.
- Verification: pytest covers basic health/API endpoints and settings import.

#### E02-T02 Model organizations, installations, repositories, and memberships

- Status: Done
- Phase: MVP
- Lane: Lane A
- Complexity: L
- Intent: Create product data models for customer organizations, users, memberships, GitHub installations, and managed repositories.
- Dependencies: E02-T01
- Acceptance criteria: Migrations exist; repository access is scoped by organization and installation.
- Verification: pytest covers model relationships and access filtering.

#### E02-T03 Implement GitHub App installation and repository selection

- Status: Done
- Phase: MVP
- Lane: Lane A
- Complexity: L
- Intent: Support GitHub App install, repository grants, organization mapping, and selected managed repositories.
- Dependencies: E02-T02
- Acceptance criteria: User can install app, grant repos, and see selected repositories in Gardener.
- Verification: Integration tests cover installation, repository add/remove, and permission errors.

#### E02-T04 Implement GitHub webhook ingestion

- Status: Done
- Phase: MVP
- Lane: Lane A
- Complexity: L
- Intent: Verify and ingest GitHub webhooks for installation, repository, push, PR, and workflow events.
- Dependencies: E02-T03
- Acceptance criteria: Webhooks are signature-verified, idempotent, and queued or stored for downstream processing.
- Verification: pytest covers valid signatures, invalid signatures, replay, and event routing.

#### E02-T05 Build dashboard shell and first-report UI from fixtures

- Status: Done
- Phase: MVP
- Lane: Lane A
- Complexity: L
- Intent: Build React/Vite dashboard shell and first-report screen using shared JSON fixtures.
- Dependencies: E00-T03
- Acceptance criteria: UI displays entropy, architecture violations, constitution questions, opportunities, session status, and PR plans from fixtures.
- Verification: Vitest covers data mapping; Playwright covers first-report route.

#### E02-T06 Connect dashboard to real backend APIs

- Status: Done
- Phase: MVP
- Lane: Lane A
- Complexity: M
- Intent: Replace fixture-only UI paths with DRF API calls through TanStack Query.
- Dependencies: E02-T01, E02-T05
- Acceptance criteria: Dashboard can render report data from API responses matching shared contracts.
- Verification: API tests and Playwright cover loading, empty, error, and success states.

## E03 Lane B - Repository Intelligence, Constitution, Entropy

### Outcome

The analysis package produces source-truth, intelligence, entropy, and opportunity contracts independent of the GitHub App UI.

#### E03-T01 Create analysis package and fixture repos

- Status: Done
- Phase: MVP
- Lane: Lane B
- Complexity: M
- Intent: Create `analysis_engine/` Python package and representative fixture repositories.
- Dependencies: E00-T02, E00-T03
- Acceptance criteria: Package imports; fixture repos cover normal repo, monorepo, missing docs, conflicting docs, and protected modules.
- Verification: pytest imports package and loads fixture repos.

#### E03-T02 Wrap Repowise indexing

- Status: Done
- Phase: MVP
- Lane: Lane B
- Complexity: XL
- Intent: Wrap the Repowise fork so Gardener can produce graph, git, health, dead-code, and docs/decision signals.
- Dependencies: E03-T01
- Acceptance criteria: A fixture repo can be indexed and normalized into `AnalysisSnapshot`.
- Verification: pytest or integration tests run indexing on fixture repos.

#### E03-T03 Implement source-truth discovery

- Status: Done
- Phase: MVP
- Lane: Lane B
- Complexity: M
- Intent: Find relevant source-truth files with deterministic file-searching tools.
- Dependencies: E03-T01
- Acceptance criteria: Discovery finds `GARDENER.md`, README, architecture docs, ADRs, agent docs, `.agents`, `.claude`, and similar files.
- Verification: Fixture tests cover complete, partial, missing, and conflicting docs.

#### E03-T04 Build Repository Constitution model

- Status: Done
- Phase: MVP
- Lane: Lane B
- Complexity: XL
- Intent: Normalize protected modules, allowed fixes, architecture boundaries, ownership, domains, test rules, ignored paths, and risk policies.
- Dependencies: E03-T03
- Acceptance criteria: `RepositoryConstitution` JSON contract is generated with evidence references, completeness score, and open questions.
- Verification: Tests cover parsing, evidence, missing data, and conflict cases.

#### E03-T05 Implement entropy scoring and forecast

- Status: Done
- Phase: MVP
- Lane: Lane B
- Complexity: XL
- Intent: Compute Repository Entropy Score with architecture 25%, maintainability 25%, knowledge 15%, testing 15%, dependency 10%, operational 10%.
- Dependencies: E03-T02, E03-T04
- Acceptance criteria: `EntropyReport` exists at repo, logical-system, module, and file level with trend/forecast fields.
- Verification: Unit tests cover weights, thresholds, missing signals, explanations, and forecast behavior.

#### E03-T06 Generate maintenance opportunities

- Status: Done
- Phase: MVP
- Lane: Lane B
- Complexity: L
- Intent: Convert analysis and entropy findings into `MaintenanceOpportunity` candidates.
- Dependencies: E03-T05
- Acceptance criteria: Opportunities include category, risk tier, confidence, affected paths, expected entropy delta, checks, and evidence.
- Verification: Fixture tests cover docs, dependency, dead-code, architecture, and protected-module cases.

## E04 Lane C - Sessions, PR Automation, Learning

### Outcome

Hosted Celery workers run gardening sessions, plan safe PRs, and learn from outcomes.

#### E04-T01 Implement Celery worker foundation

- Status: Done
- Phase: MVP
- Lane: Lane C
- Complexity: M
- Intent: Configure Redis/Celery workers for hosted session jobs.
- Dependencies: E00-T02, E02-T01
- Acceptance criteria: A Celery task can run, persist state, and report failures.
- Verification: pytest covers task execution and retry/failure behavior.

#### E04-T02 Implement session trigger system

- Status: Done
- Phase: MVP
- Lane: Lane C
- Complexity: L
- Intent: Support manual, schedule, after N commits, risky module changes, PR opened, and CI failure triggers.
- Dependencies: E04-T01, E02-T04
- Acceptance criteria: Each trigger can enqueue a hosted session with repository scope.
- Verification: Tests cover trigger creation, deduplication, and permission policy.

#### E04-T03 Implement session lifecycle from fixture contracts

- Status: Done
- Phase: MVP
- Lane: Lane C
- Complexity: L
- Intent: Execute observe, diagnose, forecast, plan, execute, and learn phases against shared JSON fixtures before real analysis is wired.
- Dependencies: E00-T03, E04-T01
- Acceptance criteria: `GardeningSessionResult` is produced from fixture opportunities and reports.
- Verification: pytest covers phase transitions, deferred work, errors, and result shape.

#### E04-T04 Implement focused PR planning

- Status: Done
- Phase: MVP
- Lane: Lane C
- Complexity: L
- Intent: Create `MaintenancePRPlan` objects for non-conflicting, policy-allowed opportunities.
- Dependencies: E04-T03, E01-T02
- Acceptance criteria: Plans include branch name, title, risk tier, confidence, changed paths, required checks, and PR body sections.
- Verification: Tests cover confidence threshold, protected paths, conflict prevention, and PR body content.

#### E04-T05 Implement GitHub branch and PR execution

- Status: Done
- Phase: MVP
- Lane: Lane C
- Complexity: XL
- Intent: Execute approved `MaintenancePRPlan` objects through GitHub REST using Python HTTP clients.
- Dependencies: E04-T04, E02-T03
- Acceptance criteria: Worker can create a branch and PR for an allowed fixture plan.
- Verification: Tests use mocked GitHub HTTP responses and cover failure/retry behavior.

#### E04-T06 Implement PR outcome learning

- Status: Open
- Phase: MVP
- Lane: Lane C
- Complexity: L
- Intent: Capture accepted, rejected, edited, merged, reverted, failed, and closed outcomes and update `GardenerProfile`.
- Dependencies: E04-T05, E02-T04
- Acceptance criteria: Outcomes update ranking signals and propose `.gardener/profile.yaml` changes.
- Verification: Tests cover outcome ingestion and memory update rules.

#### E04-T07 Implement ROI estimates

- Status: Done
- Phase: MVP
- Lane: Lane C
- Complexity: M
- Intent: Estimate engineering hours saved, hotspots removed before incidents, and maintainability improvements.
- Dependencies: E04-T03
- Acceptance criteria: Reports and PRs show conservative ROI estimates with assumptions.
- Verification: Tests cover calculation formulas and missing data.

## E05 Cross-Lane Integration

### Outcome

The three lanes move from fixture contracts to real end-to-end behavior.

#### E05-T01 Wire first real analysis into first report

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: XL
- Intent: Connect GitHub-selected repository data to Lane B analysis and display the real first report in Lane A dashboard.
- Dependencies: E02-T06, E03-T05
- Acceptance criteria: A selected fixture or test GitHub repo produces a real first report.
- Verification: End-to-end test covers install/select to first report.

#### E05-T02 Wire real opportunities into session and PR planning

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: L
- Intent: Feed Lane B `MaintenanceOpportunity` output into Lane C session and PR planning.
- Dependencies: E03-T06, E04-T04
- Acceptance criteria: Real opportunities create valid session results and PR plans.
- Verification: Integration test validates opportunity-to-plan flow.

#### E05-T03 Ship first safe maintenance PR end-to-end

- Status: Done
- Phase: MVP
- Lane: Shared
- Complexity: XL
- Intent: Run one complete Gardener flow that creates a safe focused PR on a test repository.
- Dependencies: E05-T01, E05-T02, E04-T05
- Acceptance criteria: Test repository receives a Gardener PR with evidence, confidence, entropy impact, and verification sections.
- Verification: End-to-end GitHub integration test or staged manual test.

## E06 Pricing, Billing, and ROI

### Outcome

The product can be sold by managed repository and complexity multiplier.

#### E06-T01 Model complexity multiplier

- Status: Open
- Phase: MVP
- Lane: Lane A
- Complexity: M
- Intent: Calculate multiplier from LOC, modules, and contributors.
- Dependencies: E03-T05
- Acceptance criteria: Each managed repo has transparent complexity inputs and multiplier.
- Verification: Unit tests cover size bands and edge cases.

#### E06-T02 Add billing plan foundation

- Status: Open
- Phase: MVP
- Lane: Lane A
- Complexity: M
- Intent: Track subscription plan, managed repository count, complexity multiplier, and autonomous PR add-on flag.
- Dependencies: E02-T02, E06-T01
- Acceptance criteria: Admin can view plan inputs; no payment provider is required yet.
- Verification: pytest covers model and API behavior.

## E07 Future Expansion

### Outcome

Gardener grows after the GitHub App product proves value.

#### E07-T01 Design organization-wide multi-repo intelligence

- Status: Open
- Phase: Future
- Lane: Shared
- Complexity: XL
- Intent: Aggregate health and risk across many repositories.
- Dependencies: E04-T06
- Acceptance criteria: Design supports cross-repo blast radius and shared ownership risks.
- Verification: Architecture document reviewed.

#### E07-T02 Evaluate customer-hosted deployment

- Status: Open
- Phase: Future
- Lane: Shared
- Complexity: L
- Intent: Define local hosted version for large customers that demand it.
- Dependencies: E00-T01
- Acceptance criteria: Tradeoffs, requirements, and support burden are documented.
- Verification: Deployment docs updated.
