# Shared JSON Contracts

> Status: Ground truth
> Purpose: Define lane boundaries so three engineers can work independently.

These contracts are the first technical interface between the platform, analysis, and session/PR lanes. They are intentionally stable and JSON-shaped so backend serializers, analysis fixtures, frontend mocks, and worker tests can share the same language.

Executable schemas and valid sample payloads live in `fixtures/schemas/` and `fixtures/contracts/`. Contract examples in this document are product truth; fixture schemas are the validation source for implementation work.

## Contract rules

- Use `snake_case` for JSON fields.
- Include `schema_version`.
- Include stable IDs where the product stores the object.
- Include `repository_id` and `commit_sha` whenever the object is tied to repository state.
- Include evidence references instead of raw source code where possible.
- Prefer arrays of typed objects over freeform maps for API-facing data.

## EvidenceReference

```json
{
  "source_type": "file",
  "path": "ARCHITECTURE.md",
  "section": "Boundaries",
  "line_start": 12,
  "line_end": 18,
  "summary": "UI must call API services and must not import persistence modules."
}
```

## RepositoryConstitution

Produced by Lane B. Consumed by all lanes.

```json
{
  "schema_version": "1.0",
  "repository_id": "repo_123",
  "commit_sha": "abc123",
  "completeness_score": 0.72,
  "protected_modules": [
    {
      "name": "auth",
      "paths": ["apps/api/auth/**"],
      "reason": "Security-sensitive module"
    }
  ],
  "never_touch": [
    {
      "path": "apps/api/billing/payment-engine/**",
      "reason": "Payment logic requires human-owned review"
    }
  ],
  "allowed_fixes": {
    "autonomous": ["docs", "lint_format", "dependency_patch"],
    "assisted": ["tests", "refactoring", "module_extraction"],
    "advisory": ["auth", "payments", "pricing", "permissions"]
  },
  "architecture_boundaries": [
    {
      "rule_id": "arch_001",
      "description": "UI must not import persistence modules",
      "forbidden_from": ["apps/web/**"],
      "forbidden_to": ["apps/api/**/models.py"],
      "evidence": []
    }
  ],
  "ignored_paths": ["generated/**", "migrations/**"],
  "open_questions": [
    {
      "question_id": "q_001",
      "severity": "blocking",
      "question": "Which modules are protected from autonomous refactors?",
      "evidence": []
    }
  ]
}
```

## GardenerProfile

Stored in `.gardener/profile.yaml`, but API and workers may exchange it as JSON.

```json
{
  "schema_version": "1.0",
  "repository_id": "repo_123",
  "preferred_pr_size": "small",
  "accepted_categories": ["dependency_patch", "docs"],
  "rejected_categories": ["large_refactor"],
  "reverted_categories": [],
  "learned_protected_patterns": [],
  "review_preferences": [
    "Prefer one maintenance category per PR"
  ],
  "updated_from_pr_outcomes": [
    {
      "maintenance_pr_id": "mpr_123",
      "outcome": "merged",
      "category": "dependency_patch"
    }
  ]
}
```

## AnalysisSnapshot

Produced by Lane B. Consumed by Lane A and Lane C.

```json
{
  "schema_version": "1.0",
  "analysis_snapshot_id": "snap_123",
  "repository_id": "repo_123",
  "commit_sha": "abc123",
  "created_at": "2026-06-05T12:00:00Z",
  "logical_systems": [
    {
      "logical_system_id": "sys_backend",
      "name": "Backend",
      "paths": ["apps/api/**"]
    }
  ],
  "signals": {
    "dependency_cycles": [],
    "hotspots": [],
    "dead_code_candidates": [],
    "ownership_risks": [],
    "test_gaps": [],
    "dependency_risks": [],
    "ci_failures": []
  },
  "constitution_id": "constitution_123"
}
```

## EntropyReport

Produced by Lane B. Displayed by Lane A. Used by Lane C.

```json
{
  "schema_version": "1.0",
  "entropy_report_id": "entropy_123",
  "repository_id": "repo_123",
  "analysis_snapshot_id": "snap_123",
  "commit_sha": "abc123",
  "score": {
    "overall": 42.0,
    "classification": "warning",
    "components": {
      "architecture": 18.0,
      "maintainability": 11.0,
      "knowledge": 5.0,
      "testing": 4.0,
      "dependency": 2.0,
      "operational": 2.0
    }
  },
  "scopes": [
    {
      "scope_type": "logical_system",
      "scope_id": "sys_backend",
      "name": "Backend",
      "overall": 58.0,
      "classification": "critical"
    }
  ],
  "top_contributors": [
    {
      "kind": "architecture_violation",
      "summary": "UI imports persistence module",
      "impact": 8.0,
      "evidence": []
    }
  ],
  "forecast": {
    "horizon_days": 90,
    "predicted_overall": 53.0,
    "confidence": 0.64,
    "summary": "Architecture and testing entropy are rising."
  }
}
```

## MaintenanceOpportunity

Produced by Lane B or Lane C. Displayed by Lane A. Planned by Lane C.

```json
{
  "schema_version": "1.0",
  "maintenance_opportunity_id": "opp_123",
  "repository_id": "repo_123",
  "analysis_snapshot_id": "snap_123",
  "category": "docs",
  "risk_tier": "tier_1_autonomous",
  "confidence": 0.94,
  "title": "Refresh stale architecture documentation",
  "summary": "ARCHITECTURE.md does not reflect current service boundaries.",
  "affected_paths": ["ARCHITECTURE.md", "apps/api/services/**"],
  "blocked_by": [],
  "expected_entropy_delta": -2.1,
  "required_checks": ["pytest", "docs_review"],
  "evidence": []
}
```

## GardeningSessionResult

Produced by Lane C. Displayed by Lane A.

```json
{
  "schema_version": "1.0",
  "gardening_session_id": "session_123",
  "repository_id": "repo_123",
  "trigger": {
    "type": "manual",
    "actor": "user_123"
  },
  "status": "completed",
  "started_at": "2026-06-05T12:00:00Z",
  "finished_at": "2026-06-05T12:12:00Z",
  "phase_results": [
    {
      "phase": "observe",
      "status": "completed",
      "summary": "Collected source truth and analysis signals."
    }
  ],
  "opportunities_selected": ["opp_123"],
  "opportunities_deferred": [
    {
      "maintenance_opportunity_id": "opp_456",
      "reason": "Touches protected auth module"
    }
  ],
  "maintenance_pr_plans": ["pr_plan_123"],
  "errors": []
}
```

## MaintenancePRPlan

Produced by Lane C. Executed through Lane A's GitHub integration.

```json
{
  "schema_version": "1.0",
  "maintenance_pr_plan_id": "pr_plan_123",
  "repository_id": "repo_123",
  "gardening_session_id": "session_123",
  "maintenance_opportunity_ids": ["opp_123"],
  "branch_name": "gardener/docs-architecture-refresh",
  "title": "Refresh architecture documentation",
  "risk_tier": "tier_1_autonomous",
  "confidence": 0.94,
  "changed_paths": ["ARCHITECTURE.md"],
  "pr_body_sections": {
    "goal": "Refresh stale architecture docs.",
    "evidence": "Detected stale source truth.",
    "entropy_impact": "Expected -2.1 entropy.",
    "verification": "Docs review required."
  },
  "required_checks": ["docs_review"],
  "blocked": false,
  "block_reason": null
}
```

## FirstReportFixture

Lane A should be able to build the first dashboard before the real analysis pipeline exists by consuming:

```json
{
  "repository_constitution": {},
  "analysis_snapshot": {},
  "entropy_report": {},
  "gardening_session_result": {},
  "maintenance_opportunities": [],
  "maintenance_pr_plans": []
}
```
