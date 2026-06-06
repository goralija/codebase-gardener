# User Flows

> Status: Ground truth
> Purpose: Define the workflows the product must make easy.

## Install and first report

1. User installs the GitHub App.
2. User selects repositories.
3. Gardener starts a hosted first scan.
4. Gardener searches for source-truth files and builds a draft Repository Constitution.
5. If `GARDENER.md` is missing, Gardener opens a draft PR proposing a conservative starter constitution.
6. Gardener creates ConstitutionQuestions for missing or conflicting details.
7. User receives a detailed entropy report with maintenance opportunities and architecture violations.
8. Gardener opens safe initial maintenance PRs only if policy and confidence allow it.

## Answer constitution questions

1. User opens unanswered constitution questions.
2. Gardener shows evidence from README, architecture docs, ADRs, agent docs, and inferred code.
3. User answers or edits the proposed rule.
4. Gardener updates `GARDENER.md` or opens a PR that updates it.
5. Future sessions use the clarified rule.

When the repository has no `GARDENER.md`, the first scan may already have opened a draft constitution PR. Merging or editing that PR is the customer approval step that lets future sessions move beyond `no_autonomy`.

## Review entropy and forecast

1. User opens repository report.
2. System shows Repository Entropy Score and component breakdown.
3. User drills into logical systems, modules, and files.
4. System explains contributors to score movement and forecast.
5. User opens related maintenance opportunities or architecture violations.

## Run a gardening session

1. Trigger fires manually, by schedule, after N commits, after risky module change, on PR open, or after CI failure.
2. Hosted worker checks policy and permissions.
3. Session observes repository state, diagnoses degradation, forecasts risk, ranks opportunities, executes safe work, and learns from outcomes.
4. System creates a session report and focused PRs.
5. User reviews report and PRs.

## Review a maintenance PR

1. User opens a Gardener PR.
2. PR body shows goal, evidence, confidence, changed files, entropy impact, risk tier, and verification.
3. User reviews or edits.
4. Outcome is captured as accepted, rejected, edited, merged, reverted, failed, or closed.
5. Gardener updates `.gardener/profile.yaml` through a PR or approved write path.

## Configure triggers and autonomy

1. User opens repository settings.
2. User configures triggers, protected modules, allowed fix tiers, PR frequency, and autonomy mode.
3. System validates settings against the Repository Constitution.
4. Changes are audited and applied to future sessions.
