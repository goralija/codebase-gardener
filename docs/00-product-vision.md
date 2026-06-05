# Product Vision

> Status: Ground truth
> Purpose: Define what Codebase Gardener is, who it serves, and what it must not become.

Codebase Gardener is an autonomous codebase maintenance engineer. It is built first as a sellable GitHub App for software teams with roughly 5-100 engineers that are shipping quickly while maintenance debt, anti-patterns, inconsistent agent-generated code, and architectural drift accumulate faster than the team can clean them manually.

Gardener is not only a dashboard. It must measure codebase degradation, explain why it is happening, predict where it will grow, and create focused maintenance pull requests when the risk is low enough.

## Target users

- Primary buyer: CTO, VP Engineering, Head of Engineering, or Head of Platform at a 5-100 engineer software team.
- Primary operators: engineering leads, platform engineers, and senior maintainers responsible for long-term code health.
- Secondary users: developers reviewing Gardener PRs and reading session reports.

## First customer profile

- A team with active development velocity and multiple contributors using different tools, agents, styles, and patterns.
- The team feels maintenance debt growing through inconsistent code, hallucinated abstractions, duplicate patterns, stale docs, weak tests, and architecture erosion.
- The team wants a maintenance worker that opens useful PRs, not another tool that only lists problems.

## Product promise

Gardener keeps repositories healthier while teams ship features:

- Build a deterministic Repository Constitution from source-truth files and onboarding answers.
- Fork and use Repowise as the foundation for repository intelligence.
- Compute Repository Entropy Score at repo, logical-system, module, and file level.
- Detect architectural, maintainability, knowledge, testing, dependency, operational, and light security degradation.
- Forecast degradation and rank maintenance opportunities.
- Open multiple focused, non-conflicting maintenance PRs when confidence is high.
- Learn from accepted, rejected, edited, and reverted PRs by updating repo/team memory in `.gardener/profile.yaml`.

## Non-goals

- Do not become a generic code health dashboard that only reports scores.
- Do not try to make a codebase perfect on its own.
- Do not perform big, risky changes as a v1 default.
- Do not compete head-on with full Snyk-style security scanning in v1.
- Do not silently infer architecture when source-truth files say something else.
- Do not touch protected business-critical areas unless the Repository Constitution and confidence policy explicitly allow it.

## Success criteria

Gardener is working when a team can install the GitHub App, select repositories, answer missing constitution questions, receive a detailed entropy report, review architecture violations, and get focused maintenance PRs that are small, explainable, low-risk, and useful enough that the team keeps the app enabled.
