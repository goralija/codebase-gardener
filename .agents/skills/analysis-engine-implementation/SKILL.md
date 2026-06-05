---
name: analysis-engine-implementation
description: Use when implementing Codebase Gardener analysis engine work, Repowise wrapper behavior, fixture repositories, source-truth discovery, Repository Constitution generation, entropy scoring, forecasts, or maintenance opportunity generation.
---

# Analysis Engine Implementation Skill

Use this skill for Lane B repository intelligence, constitution, and entropy work.

## Required context

Read these docs first:

1. `docs/18-technical-architecture.md`
2. `docs/19-shared-json-contracts.md`
3. `docs/16-constitution-and-memory-schema.md`
4. `docs/17-entropy-signal-catalog.md`
5. `docs/12-testing-strategy.md`

## Stack rules

- Implement the analysis engine as a Python package under `analysis_engine/`.
- Wrap the Repowise fork rather than duplicating its graph/git/health work.
- Produce JSON-compatible contract outputs: `RepositoryConstitution`, `AnalysisSnapshot`, `EntropyReport`, and `MaintenanceOpportunity`.
- Use fixture repositories for deterministic tests.

## Mandatory rules

- Use deterministic file search for source-truth discovery.
- Ask on source-truth conflicts through open questions; do not silently resolve.
- Treat inferred code behavior as evidence, not authority over explicit docs.
- Include evidence references instead of raw source code where practical.
- Support monorepos and logical systems from the start.
- Keep entropy scoring explainable and testable.

## Workflow

1. Identify the contract to produce.
2. Load fixture repo or repository checkout.
3. Run source-truth discovery or Repowise wrapper as needed.
4. Normalize output into the shared JSON contract.
5. Add pytest fixture coverage.
6. Update docs if contract shape or scoring behavior changes.

## Done criteria

- pytest validates fixture repo behavior.
- Output matches `docs/19-shared-json-contracts.md`.
- Evidence and missing-data behavior are explicit.
