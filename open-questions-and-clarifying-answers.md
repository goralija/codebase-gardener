**Product Core**

1. Is the product’s primary identity: `software entropy management platform`, `autonomous codebase maintenance engineer`, `GitHub App for codebase health`, or something else?
   * it is 'autonomous codebase maintenance engineer'
2. Who is the first ideal customer: solo devs, 5-20 engineer startups, 20-150 engineer teams, enterprise platform/security teams?
   * 5-100 engineer teams
3. What exact pain should the first paid customer feel before buying this?
   * pain of maintenance debt that accumulates with different people using different ways and tools to write code, with the need to clean anti-patterns and hallucinations that accumulate really fast in active development
4. What should Gardener explicitly not be in v1?
   * tool that tries to make codebase perfect on its own or tries to do big and risky changes, or tool that just tells the team what is the health of the codebase.
5. Should v1 optimize for “great local/developer experience” or “sellable GitHub App experience”?
   * sellable GitHub App experience

**MVP Scope**

6. For v1, should security/Snyk-style scanning be excluded, included lightly, or fully supported?
    * included lightly, security is part of any software system and needs to be maintained as any other part and factor of the system
7. Should v1 rely on Repowise as an external dependency, fork/build on it, or reimplement only selected ideas?
    * it should fork Repowise into our project and use it 
8. Which languages/ecosystems must v1 support first?
    * it should support all the langueages and frameworks and ecosystems
9. Should v1 support monorepos immediately, or only normal repos first?
    * monorepos must be supported
10. What is the first “wow” output after onboarding: entropy report, maintenance PR, architecture violations, ROI dashboard, or something else?
    * detailed entropy report with maintenance PR and arch violations

**Repository Constitution**
11. Do you want both `GARDENER.md` and `.gardener/constitution.yaml`, or only one canonical config?
    * GARDENER.md
12. What source-truth precedence should be final: `.gardener`, ADRs, `ARCHITECTURE.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `.agents`, `.claude`, inferred code?
    * there should be some pass with basic file-searching tools, that finds all of those relevant files and makes a full picture about the codebase
13. If source-truth files conflict, should Gardener stop, ask, or follow highest-precedence source and report violations?
    * the best thing is to ask
14. What must a Repository Constitution contain: protected modules, allowed fixes, architecture boundaries, ownership, domains, test rules, ignored paths, risk policies?
    * all of those are relevant in what the Gardener will do, so all of that should be there
15. When a repo has weak docs, should Gardener generate a draft constitution, ask onboarding questions, or run in conservative mode?
    * Gardener should make a background pass with draft for itself, but the onboarding questions should be created, and in the next run onboarding questions should clarify all the inconsistencies

**Entropy And Scoring**
16. Do you accept the six-part entropy model: architecture 25%, maintainability 25%, knowledge 15%, testing 15%, dependency 10%, operational 10%?
    * yes
17. Should entropy be repo-level only, or also system/module/file-level?
    * all of those
18. What thresholds should matter: healthy, warning, critical, no-autonomy?
    * all of those
19. Should the main metric be called `Repository Entropy Score`, `Codebase Sustainability Score`, or something else?
    * Repository Entropy Score
20. Should predictions be required in v1, or should v1 only track current score plus trend?
    * full autonomy must be included, not only current score plus trend

**Gardening Sessions**
21. What triggers should v1 support: manual, schedule, after N commits, after risky module changes, PR opened, CI failure?
    * all of those
22. Should one session create one combined “Weekly Gardening PR” or multiple focused PRs?
    * multiple focused PRs which must not interfere with one another 
23. What is the exact lifecycle you want: observe, diagnose, forecast, plan, execute, learn?
    * exactly that
24. Should sessions run in GitHub Actions/customer infra, Gardener-hosted workers, or both?
    * Gardener-hosted workers

**Autonomy And PR Safety**
25. What fixes are Tier 1 autonomous in v1: dependency patch, dead code, docs, lint/format, generated refresh, tests?
    * docs, lint/format-only changes, generated refreshes, dependency patches with passing checks, and dead-code removal only with very high evidence
26. What fixes are Tier 2 draft-only?
    * tests, refactoring, module extraction, layer violation repair, complexity reduction, and minor/major dependency upgrades
27. What code is never touched: auth, payments, pricing, permissions, business workflows, migrations?
    * auth, payments, pricing, permissions, business workflows, migrations, security-sensitive code, and customer-defined protected modules
28. Is `confidence >= 90%` the right threshold for creating PRs?
    * yes, unless the Repository Constitution sets a stricter threshold
29. Should auto-merge after CI ever be allowed, or should Gardener only open PRs?
    * v1 should only open PRs and should not auto-merge

**Learning And Memory**
30. Should Gardener learn from accepted/rejected/reverted PRs in v1?
    * yes, it should write into the codebase 'source truth' files
31. Where should repo/team memory live: `.gardener/profile.yaml`, hosted DB, GitHub metadata, or all?
    * repo/team memory should live in .gardener/profile.yaml
32. Should learned preferences ever override explicit constitution rules? I assume no.
    * no

**Pricing And Business**
33. Do you want pricing to be `base per managed repo * complexity multiplier`, with autonomous PRs as an add-on?
    * yes
34. What should the complexity multiplier use: LOC, modules, contributors, commit velocity, dependency graph size, repo age?
    * LOC, modules and contributors
35. Should there be a free tier, trial, or open-source/local version?
    * none of that except the local hosted version on customer machines, if some huge customer demands it in the future
36. What ROI claims are acceptable: engineering hours saved, entropy reduced, hotspots removed, incidents prevented, PRs merged?
    * engineering hours saved, hotspots removed before incidents, cleaner and more maintainable codebase

**Docs And Skills**
37. Should I create product docs only, or also implementation docs like architecture, roadmap, data model, GitHub App flow, and constitution schema?
    * all of those
38. Are `.agents/skills` meant to guide agents developing this repo, to become runtime Gardener skills for customer repos, or both?
    * first one
39. Which skills do you want first: `repo-constitution-builder`, `entropy-modeler`, `gardening-session-planner`, `safe-pr-author`, `product-spec-maintainer`?
    * those look good, if you think some others are essential, those should be included too
40. Should these skills be deterministic/checklist-heavy, with scripts and schemas, rather than broad prose instructions?
    * deterministic as more as possible
