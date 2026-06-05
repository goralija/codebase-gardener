---
name: entropy-modeler
description: Use when designing or changing Repository Entropy Score, entropy signals, thresholds, component weights, forecasts, score explanations, ROI links, or entropy-related tests.
---

# Entropy Modeler Skill

Use this skill for scoring, signal, forecast, and report logic.

## Required context

Read these docs first:

1. `docs/17-entropy-signal-catalog.md`
2. `docs/04-feature-map.md`
3. `docs/09-autonomy-and-automation-rules.md`
4. `docs/19-shared-json-contracts.md`
5. `docs/12-testing-strategy.md`

Read `docs/16-constitution-and-memory-schema.md` if score behavior depends on protected modules, architecture boundaries, ignored paths, or autonomy policy.

## Mandatory scoring rules

- Main metric is `Repository Entropy Score`.
- Higher score means higher degradation risk.
- Compute at repository, logical-system, module, and file level.
- Use these component weights unless the docs are explicitly changed:
  - architecture: 25%
  - maintainability: 25%
  - knowledge: 15%
  - testing: 15%
  - dependency: 10%
  - operational: 10%
- Explain score movement with evidence.
- Output must fit the `EntropyReport` contract.
- Show trend and forecast when possible.
- Do not use unavailable signals as if they are known.

## Modeling workflow

1. Identify the scope: repo, logical system, module, or file.
2. Identify available raw signals and missing signals.
3. Map signals to entropy components.
4. Normalize and weight scores.
5. Classify thresholds: healthy, warning, critical, no-autonomy.
6. Explain top contributors and confidence.
7. Define tests with fixture repos or synthetic signals.

## Avoid

- Magic scores that cannot be traced to evidence.
- A single overall score without component breakdown.
- Forecasts that hide low confidence.
- Treating security as the whole product.
- Allowing high entropy alone to justify risky autonomous changes.

## Done criteria

- Component weights are tested.
- Missing data behavior is tested.
- Explanations include evidence.
- Score changes update docs if product truth changes.
