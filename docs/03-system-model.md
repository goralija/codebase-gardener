# System Model

> Status: Ground truth
> Purpose: Define the main product entities and relationships.

## Core entities

### Customer and access

- CustomerOrganization: billing and ownership unit mapped to a GitHub organization or account.
- User: a person using Gardener.
- Membership: a user's role inside a CustomerOrganization.
- GitHubInstallation: GitHub App installation and granted repository access.

### Repository management

- ManagedRepository: a repository selected for Gardener sessions and billing.
- LogicalSystem: a detected or configured subsystem inside a repo or monorepo.
- Module: a code area inside a repository or logical system.
- RepositoryConstitution: parsed, normalized model derived from source-truth files and onboarding answers.
- ConstitutionQuestion: unresolved question Gardener asks when source truth is weak, missing, or conflicting.
- GardenerProfile: learned repo/team memory stored in `.gardener/profile.yaml`.

### Analysis and entropy

- AnalysisSnapshot: captured repository state for one point in time.
- EntropyScore: repo/system/module/file score with component breakdown.
- Signal: raw or derived evidence used by scoring and diagnosis.
- ArchitectureViolation: conflict between source-truth rules and observed code.
- MaintenanceOpportunity: ranked candidate action.
- Forecast: predicted degradation or expected improvement.

### Sessions and PRs

- GardeningSession: hosted run with observe, diagnose, forecast, plan, execute, and learn phases.
- SessionTrigger: manual, schedule, after N commits, risky module change, PR opened, CI failure.
- MaintenancePlan: selected opportunities for a session.
- MaintenancePR: focused GitHub PR created by Gardener.
- PROutcome: accepted, rejected, edited, merged, reverted, closed, or failed.

### Billing and ROI

- ComplexityMultiplier: multiplier based on LOC, modules, and contributors.
- Subscription: base managed-repository plan and add-ons.
- ROIEstimate: engineering hours saved, hotspots removed before incidents, and maintainability improvements.

## Relationship rules

- A CustomerOrganization has many GitHubInstallations and ManagedRepositories.
- A ManagedRepository has one current RepositoryConstitution and many historical AnalysisSnapshots.
- A ManagedRepository may contain many LogicalSystems, especially in monorepos.
- EntropyScore can attach to repository, logical system, module, or file.
- MaintenanceOpportunity must be traceable to signals, constitution rules, and score impact.
- MaintenancePR must belong to one GardeningSession and one focused opportunity group.

## Lifecycle rules

- Constitutions are built from source truth and onboarding answers, not from freeform agent guesses.
- Conflicts in source truth create ConstitutionQuestions.
- Sessions can run with a draft internal constitution, but autonomy must be limited until critical questions are answered.
- Learned memory never overrides explicit constitution rules.
- PR outcomes feed learning and future ranking.
