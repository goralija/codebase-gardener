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
7. Gardener stores and promotes the first analysis as the repository baseline.
8. User receives a detailed entropy report with maintenance opportunities and architecture violations.
9. Gardener does not open maintenance PRs during the first scan.

## Answer constitution questions

1. User opens unanswered constitution questions.
2. Gardener shows evidence from README, architecture docs, ADRs, agent docs, and inferred code.
3. User answers or edits the proposed rule.
4. Gardener updates `GARDENER.md` or opens a PR that updates it.
5. Future sessions use the clarified rule.

When the repository has no `GARDENER.md`, a hosted analysis session may already have opened a draft constitution PR. Merging or editing that PR is the customer approval step that lets future sessions move beyond `no_autonomy`.

## Review entropy and forecast

1. User opens repository report.
2. System shows Repository Entropy Score and component breakdown.
3. User drills into logical systems, modules, and files.
4. System explains contributors to score movement and forecast.
5. User opens related maintenance opportunities or architecture violations.

## Run a gardening session

1. Trigger fires manually, by schedule, after N commits, after risky module change, on PR open, or after CI failure.
2. Hosted worker checks policy and permissions.
3. Session loads the latest promoted repository baseline.
4. Session observes current repository state and stores the current analysis.
5. If no baseline exists, the current analysis is promoted as the baseline and no maintenance PRs are planned; if `GARDENER.md` is missing, Gardener may open a draft starter constitution PR.
6. If a baseline exists, Gardener compares current analysis to the baseline, diagnoses drift, forecasts risk, ranks drift-relevant opportunities, executes safe work, and learns from outcomes.
7. For manual sessions with no drift-relevant opportunities, Gardener may plan from current opportunities that are not already covered by an active unblocked Gardener PR plan.
8. System creates a session report plus focused PRs or blocked PR plans explaining policy gates.
9. Every completed non-first-scan session promotes its current analysis as the latest relevant baseline.
10. User reviews report and PRs.

## Review a maintenance PR

1. User opens a Gardener PR.
2. PR body shows goal, evidence, confidence, changed files, entropy impact, risk tier, and verification.
3. User reviews or edits.
4. Outcome is captured as accepted, rejected, edited, merged, reverted, failed, or closed.
5. Gardener updates `.gardener/profile.yaml` through a PR or approved write path.
6. When all Gardener-authored PRs from the session are merged or closed, Gardener runs a post-PR refresh analysis and promotes it as the latest baseline.
7. If a merged Gardener PR is reverted later, Gardener records the revert and runs another baseline refresh because default-branch state changed again.

## Configure triggers and autonomy

1. User opens repository settings.
2. New repositories start quiet: manual sessions are enabled, automated triggers are disabled, and autonomy mode is conservative.
3. User configures triggers, protected modules, allowed fix tiers, PR frequency, and autonomy mode.
4. System validates settings against the latest promoted Repository Constitution baseline.
5. Changes are audited and applied to future sessions.
