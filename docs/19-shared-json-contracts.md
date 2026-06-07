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

## AnalysisDriftReport

Produced by Lane B/Lane C comparison logic. Consumed by session planning,
reports, and PR body evidence.

```json
{
  "schema_version": "1.0",
  "repository_id": "repo_123",
  "baseline_analysis_id": "analysis_base",
  "baseline_commit_sha": "abc123",
  "current_analysis_id": "analysis_current",
  "current_commit_sha": "def456",
  "generated_at": "2026-06-07T12:00:00Z",
  "no_baseline": false,
  "entropy_delta": {
    "overall": 6.5,
    "components": {
      "architecture": 2.0,
      "maintainability": 3.0,
      "testing": 1.5
    }
  },
  "signal_changes": {
    "new": [
      {
        "bucket": "test_gaps",
        "path": "backend/apps/sessions/tasks.py",
        "kind": "test_gap",
        "summary": "Session baseline promotion lacks regression coverage.",
        "impact": 3.0
      }
    ],
    "worsened": [
      {
        "bucket": "hotspots",
        "path": "backend/apps/sessions/tasks.py",
        "kind": "hotspot",
        "summary": "Session worker changed frequently and owns more lifecycle logic.",
        "impact": 12.0,
        "baseline_impact": 5.0,
        "current_impact": 12.0,
        "impact_delta": 7.0
      }
    ],
    "resolved": [],
    "unchanged_count": 4
  },
  "hotspot_paths": [
    {
      "path": "backend/apps/sessions/tasks.py",
      "change_count": 2,
      "impact_delta": 10.0,
      "reasons": [
        "Session worker changed frequently and owns more lifecycle logic.",
        "Session baseline promotion lacks regression coverage."
      ]
    }
  ],
  "summary": {
    "new_count": 1,
    "worsened_count": 1,
    "resolved_count": 0,
    "unchanged_count": 4
  }
}
```

Signal summaries must identify bucket, path, kind, summary, and impact without
raw source code. `no_baseline` is true only for comparison-only callers without
a prior baseline; the hosted session worker treats no-baseline sessions as
baseline-only and does not plan PRs. Non-first automated sessions plan from new
or worsened drift; manual sessions may fall back to current opportunities when
no drift-relevant opportunities exist and no active unblocked Gardener PR plan
already covers the opportunity.

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
  "baseline_analysis_id": "analysis_base",
  "baseline_commit_sha": "abc123",
  "current_analysis_id": "analysis_current",
  "current_commit_sha": "def456",
  "post_pr_refresh_analysis_id": null,
  "drift_report": null,
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

The analysis ID/commit fields and `drift_report` are optional for compatibility
with older fixtures. First-scan and no-baseline sessions set `drift_report` to
null because they do not compare against a previous baseline.

`errors[]` entries include `phase` and `message`. Execute-phase errors for a
specific PR plan may also include `maintenance_pr_plan_id` so the session can
continue with other approved plans while reporting which plan failed.

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
  "confidence_threshold": 0.9,
  "changed_paths": ["ARCHITECTURE.md"],
  "pr_body_sections": {
    "goal": "Refresh stale architecture docs.",
    "evidence": "Detected stale source truth.",
    "entropy_impact": "Expected -2.1 entropy.",
    "verification": "Docs review required.",
    "roi_impact": "Estimated 0.2–0.5 engineering hours saved. Assumptions: 0.5 hrs/file for docs; confidence 0.94; conservative scale 0.5–1.0×. Estimates are conservative and indicative only."
  },
  "required_checks": ["docs_review"],
  "blocked": false,
  "block_reason": null,
  "terminal_outcome": null,
  "terminal_outcome_at": null
}
```

`confidence_threshold` is optional for `schema_version` 1.0 compatibility. Consumers that do
not receive it must apply the default autonomous PR threshold of `0.9`.
`terminal_outcome` is null until a Gardener-authored PR is merged, closed, or
reverted. Plan outcome history is append-only in backend storage and is not
part of the compact public plan contract.

## RepositoryAutomationSettings

Produced by Lane A backend. Displayed and edited by Lane A dashboard.

```json
{
  "schema_version": "1.0",
  "repository": {
    "id": "repo_123",
    "full_name": "acme/api",
    "default_branch": "main",
    "html_url": "https://github.com/acme/api"
  },
  "baseline": {
    "analysis_id": null,
    "commit_sha": null,
    "source": null,
    "promoted_at": null
  },
  "policy": {
    "id": "policy_123",
    "autonomy_mode": "conservative",
    "manual_trigger_enabled": true,
    "scheduled_trigger_enabled": false,
    "commit_trigger_enabled": false,
    "risky_module_trigger_enabled": false,
    "pr_opened_trigger_enabled": false,
    "ci_failure_trigger_enabled": false,
    "commit_threshold": 10,
    "created_at": "2026-06-06T08:00:00Z",
    "updated_at": "2026-06-06T08:00:00Z"
  },
  "effective": {
    "autonomous_pr_add_on_enabled": true,
    "can_create_autonomous_prs": false,
    "pr_creation_status": "Repository autonomy mode is Conservative; sessions report recommendations without PR creation.",
    "default_commit_threshold": 10,
    "confidence_threshold": 0.9
  },
  "permissions": {
    "can_edit": true,
    "can_trigger_manual_session": true
  },
  "recent_sessions": [],
  "recent_pr_plans": []
}
```

`autonomy_mode` values are `conservative`, `assisted`, and `autonomous`.
`commit_threshold` must be between 1 and 500. Owner, admin, and maintainer roles
may update repository automation policy and trigger manual sessions. Viewer and
reviewer roles may view settings but may not update them.
New repositories use the quiet defaults shown above until the user explicitly
enables automated triggers or a higher autonomy mode.

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
