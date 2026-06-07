import copy
import logging
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from jsonschema import Draft202012Validator

from apps.analysis.fixtures import _schema_registry, _schema_path, _load_json
from apps.billing.models import Subscription
from apps.maintenance_prs.models import MaintenancePRPlanOpportunity
from apps.maintenance_prs.policy import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    configured_confidence_threshold,
)
from apps.maintenance_prs.planner import (
    plan_maintenance_prs,
    serialize_maintenance_pr_plan,
)
from apps.triggers.models import RepositoryAutomationPolicy
from apps.triggers.policy import CONSERVATIVE_AUTONOMY_PR_BLOCK_REASON
from tests.test_product_models import create_installation, create_organization, create_repository


@pytest.mark.django_db
def test_planner_persists_grouped_contract_shaped_pr_plan():
    repository = demo_repository()
    opportunities = [
        opportunity("opp_docs_a", "Refresh API docs", ["docs/api.md"]),
        opportunity("opp_docs_b", "Refresh architecture docs", ["docs/architecture.md"]),
    ]

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_grouped",
        opportunities=opportunities,
        constitution=constitution(),
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.repository == repository
    assert plan.title == "Plan 2 docs maintenance opportunities"
    assert plan.branch_name == "gardener/docs-refresh-api-docs"
    assert not plan.blocked
    assert plan.changed_paths == ["docs/api.md", "docs/architecture.md"]
    assert sorted(plan.opportunity_links.values_list("maintenance_opportunity_id", flat=True)) == [
        "opp_docs_a",
        "opp_docs_b",
    ]

    contract = serialize_maintenance_pr_plan(plan)
    validator = Draft202012Validator(
        _load_json(_schema_path("maintenance_pr_plan.schema.json")),
        registry=_schema_registry(),
    )
    assert not list(validator.iter_errors(contract))
    assert contract["maintenance_opportunity_ids"] == ["opp_docs_a", "opp_docs_b"]
    assert set(contract["pr_body_sections"]) == {
        "goal",
        "evidence",
        "entropy_impact",
        "verification",
        "roi_impact",
    }
    assert "hours saved" in contract["pr_body_sections"]["roi_impact"]
    assert "Assumptions" in contract["pr_body_sections"]["roi_impact"]
    assert "Minimum opportunity confidence 0.94" in contract["pr_body_sections"]["verification"]
    assert "Changed paths: docs/api.md, docs/architecture.md" in contract["pr_body_sections"]["verification"]
    assert "Categories checked against constitution allowed fixes: docs" in contract["pr_body_sections"]["evidence"]


def test_maintenance_pr_plan_contract_accepts_legacy_threshold_omission():
    contract = _load_json(
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "contracts"
        / "maintenance_pr_plan.json"
    )
    contract.pop("confidence_threshold")
    validator = Draft202012Validator(
        _load_json(_schema_path("maintenance_pr_plan.schema.json")),
        registry=_schema_registry(),
    )

    assert not list(validator.iter_errors(contract))


def test_confidence_threshold_env_override_parser(monkeypatch):
    monkeypatch.setenv("GARDENER_CONFIDENCE_THRESHOLD", "0.50")
    assert configured_confidence_threshold() == 0.5

    monkeypatch.setenv("GARDENER_CONFIDENCE_THRESHOLD", "50")
    assert configured_confidence_threshold() == 0.5

    monkeypatch.setenv("GARDENER_CONFIDENCE_THRESHOLD", "not-a-number")
    assert configured_confidence_threshold() == 0.85


@pytest.mark.django_db
def test_planner_keeps_groups_focused_by_size_category_and_path_conflict():
    repository = demo_repository()
    opportunities = [
        opportunity("opp_docs_a", "Docs A", ["docs/a.md"]),
        opportunity("opp_docs_b", "Docs B", ["docs/b.md"]),
        opportunity("opp_docs_c", "Docs C", ["docs/c.md"]),
        opportunity("opp_docs_d", "Docs D", ["docs/d.md"]),
        opportunity("opp_lint", "Lint", ["src/app.py"], category="lint_format"),
        opportunity("opp_overlap", "Docs overlap", ["docs/a.md"]),
    ]

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_focus",
        opportunities=opportunities,
        constitution=constitution(),
    )

    grouped_counts = [
        plan.opportunity_links.count()
        for plan in plans
        if not plan.blocked and plan.risk_tier == "tier_1_autonomous"
    ]
    assert sorted(grouped_counts) == [1, 1, 3]
    blocked = [plan for plan in plans if plan.blocked]
    assert len(blocked) == 1
    assert blocked[0].block_reason == "Opportunity conflicts with another selected PR plan in this session."


@pytest.mark.django_db
def test_planner_does_not_bundle_into_force_blocked_group():
    # opp_b is force-blocked because it conflicts with opp_a's path. opp_c shares
    # opp_b's category but has no real path conflict, so it must get its own
    # unblocked plan instead of being merged into (and blocked with) opp_b.
    repository = demo_repository()
    opportunities = [
        opportunity("opp_a", "Docs A", ["docs/a.md"]),
        opportunity("opp_b", "Lint conflict", ["docs/a.md"], category="lint_format"),
        opportunity("opp_c", "Lint clean", ["src/other.py"], category="lint_format"),
    ]

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_force_block",
        opportunities=opportunities,
        constitution=constitution(),
    )

    by_opportunity = {
        plan.opportunity_links.first().maintenance_opportunity_id: plan
        for plan in plans
        if plan.opportunity_links.count() == 1
    }
    assert not by_opportunity["opp_a"].blocked
    assert by_opportunity["opp_b"].blocked
    assert by_opportunity["opp_b"].block_reason == (
        "Opportunity conflicts with another selected PR plan in this session."
    )
    # The clean opportunity is not bundled into the force-blocked plan.
    assert not by_opportunity["opp_c"].blocked
    assert by_opportunity["opp_c"].opportunity_links.count() == 1


@pytest.mark.django_db
def test_planner_blocks_low_confidence_and_protected_work_but_allows_assisted_drafts():
    repository = demo_repository()
    low_confidence = max(0.0, DEFAULT_CONFIDENCE_THRESHOLD - 0.01)
    opportunities = [
        opportunity("opp_low", "Low confidence", ["docs/low.md"], confidence=low_confidence),
        opportunity("opp_protected", "Billing docs", ["backend/apps/billing/models.py"]),
        opportunity(
            "opp_assisted",
            "Extract module",
            ["src/module.py"],
            category="refactoring",
            risk_tier="tier_2_assisted",
        ),
    ]

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_blocked",
        opportunities=opportunities,
        constitution=constitution(),
    )

    assert len(plans) == 3
    reasons = {plan.opportunity_links.first().maintenance_opportunity_id: plan.block_reason for plan in plans}
    assert reasons["opp_low"] == (
        f"Confidence below {DEFAULT_CONFIDENCE_THRESHOLD:.2f} PR creation threshold."
    )
    assert reasons["opp_protected"].startswith("Path backend/apps/billing/models.py matches protected module")
    assert reasons["opp_assisted"] is None
    assert {plan.blocked for plan in plans} == {False, True}


@pytest.mark.django_db
def test_planner_logs_blocked_plan_reason(caplog):
    caplog.set_level(logging.INFO, logger="apps.maintenance_prs.planner")
    repository = demo_repository()
    low_confidence = max(0.0, DEFAULT_CONFIDENCE_THRESHOLD - 0.01)

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_blocked_logs",
        opportunities=[
            opportunity(
                "opp_low",
                "Low confidence",
                ["docs/low.md"],
                confidence=low_confidence,
            )
        ],
        constitution=constitution(),
    )

    blocked_records = [
        record
        for record in caplog.records
        if record.message == "maintenance_pr_plan.blocked"
    ]
    assert len(blocked_records) == 1
    record = blocked_records[0]
    assert record.maintenance_pr_plan_id == str(plans[0].id)
    assert record.gardening_session_id == "session_blocked_logs"
    assert record.maintenance_opportunity_ids == ["opp_low"]
    assert record.block_reason == (
        f"Confidence below {DEFAULT_CONFIDENCE_THRESHOLD:.2f} PR creation threshold."
    )
    assert record.changed_path_count == 1


@pytest.mark.django_db
def test_planner_sanitizes_legacy_generated_required_checks():
    repository = demo_repository()
    stale = opportunity("opp_stale", "Refresh docs", ["docs/guide.md"])
    stale["required_checks"] = [
        "pytest",
        "python -m pytest",
        "uv run pytest",
        "dependency_audit",
        "docs_review",
    ]

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_legacy_checks",
        opportunities=[stale],
        constitution=constitution(),
    )

    assert plans[0].required_checks == ["docs_review"]
    verification = plans[0].pr_body_sections["verification"]
    assert "Required checks: docs_review." in verification
    assert "pytest" not in verification
    assert "dependency_audit" not in verification


@pytest.mark.django_db
def test_planner_reports_policy_markers_as_concrete_block_reasons():
    repository = demo_repository()
    low_confidence_value = max(0.0, DEFAULT_CONFIDENCE_THRESHOLD - 0.01)
    low_confidence = opportunity(
        "opp_low_marker",
        "Patch dependency",
        ["backend/pyproject.toml"],
        category="dependency_patch",
        confidence=low_confidence_value,
    )
    low_confidence["blocked_by"] = ["below_confidence_threshold"]
    protected = opportunity(
        "opp_protected_marker",
        "Refresh billing docs",
        ["backend/apps/billing/models.py"],
        risk_tier="tier_3_advisory",
    )
    protected["blocked_by"] = ["protected_module:billing"]
    prerequisite = opportunity(
        "opp_prerequisite",
        "Refresh follow-up docs",
        ["docs/follow-up.md"],
    )
    prerequisite["blocked_by"] = ["opp_low_marker"]

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_policy_markers",
        opportunities=[low_confidence, protected, prerequisite],
        constitution=constitution(),
    )

    reasons = {
        plan.opportunity_links.first().maintenance_opportunity_id: plan.block_reason
        for plan in plans
    }
    verification = {
        plan.opportunity_links.first().maintenance_opportunity_id: plan.pr_body_sections[
            "verification"
        ]
        for plan in plans
    }
    assert reasons["opp_low_marker"] == (
        f"Confidence below {DEFAULT_CONFIDENCE_THRESHOLD:.2f} PR creation threshold."
    )
    assert verification["opp_low_marker"].startswith(
        f"Blocked: Confidence below {DEFAULT_CONFIDENCE_THRESHOLD:.2f} "
        "PR creation threshold. Required checks:"
    )
    assert reasons["opp_protected_marker"].startswith(
        "Path backend/apps/billing/models.py matches protected module billing"
    )
    assert reasons["opp_prerequisite"] == (
        "Opportunity is blocked by prerequisite work: opp_low_marker."
    )


@pytest.mark.django_db
def test_planner_persists_stricter_confidence_threshold_from_constitution():
    repository = demo_repository()
    strict_constitution = constitution()
    strict_constitution["risk_policies"] = {"confidence_threshold": 0.95}

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_strict_threshold",
        opportunities=[opportunity("opp_docs", "Refresh docs", ["docs/a.md"], confidence=0.94)],
        constitution=strict_constitution,
    )

    assert plans[0].blocked
    assert plans[0].confidence_threshold == 0.95
    assert plans[0].block_reason == "Confidence below 0.95 PR creation threshold."


@pytest.mark.django_db
def test_dependency_patch_at_default_threshold_can_plan_autonomous_pr():
    repository = demo_repository()

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_dependency_threshold",
        opportunities=[
            opportunity(
                "opp_dependency",
                "Patch dependency",
                ["backend/pyproject.toml"],
                category="dependency_patch",
                confidence=DEFAULT_CONFIDENCE_THRESHOLD,
            )
        ],
        constitution=constitution(),
    )

    assert len(plans) == 1
    assert not plans[0].blocked
    assert plans[0].confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


@pytest.mark.django_db
def test_tests_opportunities_stay_separate_pr_plans():
    repository = demo_repository()

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_test_gap_split",
        opportunities=[
            opportunity(
                "opp_tests_app",
                "Add App coverage",
                ["src/frontend/src/App.tsx"],
                category="tests",
                risk_tier="tier_2_assisted",
                confidence=0.94,
            ),
            opportunity(
                "opp_tests_auth",
                "Add AuthLayout coverage",
                ["src/frontend/src/features/auth/AuthLayout.tsx"],
                category="tests",
                risk_tier="tier_2_assisted",
                confidence=0.94,
            ),
        ],
        constitution=constitution(),
    )

    assert len(plans) == 2
    assert [plan.changed_paths for plan in plans] == [
        ["src/frontend/src/App.tsx"],
        ["src/frontend/src/features/auth/AuthLayout.tsx"],
    ]


@pytest.mark.django_db
def test_planner_persists_dead_code_confidence_threshold():
    repository = demo_repository()
    dead_code_constitution = constitution()
    dead_code_constitution["allowed_fixes"]["autonomous"].append("dead_code")

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_dead_code",
        opportunities=[
            opportunity(
                "opp_dead_code",
                "Remove dead code",
                ["src/unused.py"],
                category="dead_code",
                confidence=0.94,
            )
        ],
        constitution=dead_code_constitution,
    )

    assert plans[0].blocked
    assert plans[0].confidence_threshold == 0.95
    assert plans[0].block_reason == "Dead-code removal requires confidence >= 0.95."


@pytest.mark.django_db
def test_planner_accepts_legacy_dead_code_removal_allowed_fix_alias():
    repository = demo_repository()
    legacy_constitution = constitution()
    legacy_constitution["allowed_fixes"]["autonomous"].append("dead_code_removal")

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_dead_code_alias",
        opportunities=[
            opportunity(
                "opp_dead_code_alias",
                "Remove dead code",
                ["src/unused.py"],
                category="dead_code",
                confidence=0.99,
            )
        ],
        constitution=legacy_constitution,
    )

    assert not plans[0].blocked


@pytest.mark.django_db
def test_planner_blocks_only_blocking_open_constitution_questions():
    repository = demo_repository()
    nonblocking_constitution = constitution()
    nonblocking_constitution["open_questions"] = [
        {"question_id": "q_info", "severity": "info", "question": "Optional preference?"}
    ]
    blocking_constitution = constitution()
    blocking_constitution["open_questions"] = [
        {"question_id": "q_blocking", "severity": "blocking", "question": "Protected paths?"}
    ]

    unblocked = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_nonblocking_question",
        opportunities=[opportunity("opp_docs_nonblocking", "Refresh docs", ["docs/a.md"])],
        constitution=nonblocking_constitution,
    )
    blocked = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_blocking_question",
        opportunities=[opportunity("opp_docs_blocking", "Refresh docs", ["docs/b.md"])],
        constitution=blocking_constitution,
    )

    assert not unblocked[0].blocked
    assert blocked[0].blocked
    assert blocked[0].block_reason == "Repository constitution has unresolved open questions."


@pytest.mark.django_db
def test_planner_is_idempotent_per_session_opportunity():
    repository = demo_repository()
    first = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_dupe",
        opportunities=[opportunity("opp_docs", "Refresh docs", ["docs/a.md"])],
        constitution=constitution(),
    )
    second = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_dupe",
        opportunities=[opportunity("opp_docs", "Refresh docs", ["docs/a.md"])],
        constitution=constitution(),
    )

    assert len(first) == 1
    assert second == []
    assert MaintenancePRPlanOpportunity.objects.filter(
        plan__repository=repository,
        plan__gardening_session_id="session_dupe",
        maintenance_opportunity_id="opp_docs",
    ).count() == 1


@pytest.mark.django_db
def test_opportunity_link_rejects_duplicate_session_opportunity():
    repository = demo_repository()
    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_validation",
        opportunities=[
            opportunity("opp_docs_a", "Refresh docs A", ["docs/a.md"]),
            opportunity("opp_docs_b", "Refresh docs B", ["docs/b.md"]),
            opportunity("opp_docs_c", "Refresh docs C", ["docs/c.md"]),
            opportunity("opp_docs_d", "Refresh docs D", ["docs/d.md"]),
        ],
        constitution=constitution(),
    )

    with pytest.raises(ValidationError):
        MaintenancePRPlanOpportunity.objects.create(
            plan=plans[-1],
            maintenance_opportunity_id="opp_docs_a",
        )


@pytest.mark.django_db
def test_profile_rejected_category_defers_opportunity():
    repository = demo_repository()
    profile = {
        "schema_version": "1.0",
        "repository_id": "repo_demo",
        "rejected_categories": ["docs"],
    }

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_profile_rejected",
        opportunities=[opportunity("opp_docs", "Refresh docs", ["docs/a.md"])],
        constitution=constitution(),
        profile=profile,
    )

    assert plans[0].blocked
    assert plans[0].block_reason == (
        "Category previously rejected by reviewers; deferred by learned profile."
    )


@pytest.mark.django_db
def test_profile_reverted_category_raises_confidence_threshold():
    repository = demo_repository()
    profile = {
        "schema_version": "1.0",
        "repository_id": "repo_demo",
        "reverted_categories": ["docs"],
    }

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_profile_reverted",
        opportunities=[opportunity("opp_docs", "Refresh docs", ["docs/a.md"], confidence=0.94)],
        constitution=constitution(),
        profile=profile,
    )

    assert plans[0].blocked
    assert plans[0].confidence_threshold == 0.97
    assert plans[0].block_reason == "Confidence below 0.97 PR creation threshold."


@pytest.mark.django_db
def test_profile_accepted_category_ranks_ahead_of_peers():
    repository = demo_repository()
    profile = {
        "schema_version": "1.0",
        "repository_id": "repo_demo",
        "accepted_categories": ["lint_format"],
    }

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_profile_accepted",
        opportunities=[
            opportunity("opp_docs", "Refresh docs", ["docs/a.md"], confidence=0.94),
            opportunity(
                "opp_lint",
                "Format module",
                ["src/app.py"],
                category="lint_format",
                confidence=0.94,
            ),
        ],
        constitution=constitution(),
        profile=profile,
    )

    # Accepted category is planned first despite equal confidence.
    assert plans[0].category == "lint_format"


@pytest.mark.django_db
def test_constitution_block_reason_wins_over_profile_rejection():
    repository = demo_repository()
    profile = {
        "schema_version": "1.0",
        "repository_id": "repo_demo",
        "rejected_categories": ["docs"],
    }
    blocking_constitution = constitution()
    blocking_constitution["open_questions"] = [
        {"question_id": "q_blocking", "severity": "blocking", "question": "Protected paths?"}
    ]

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_constitution_wins",
        opportunities=[opportunity("opp_docs", "Refresh docs", ["docs/a.md"])],
        constitution=blocking_constitution,
        profile=profile,
    )

    assert plans[0].blocked
    assert plans[0].block_reason == "Repository constitution has unresolved open questions."


@pytest.mark.django_db
def test_autonomous_pr_add_on_disabled_does_not_block_allowed_plans():
    repository = demo_repository(autonomous_pr_add_on_enabled=False)

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_billing_gate",
        opportunities=[
            opportunity("opp_docs_a", "Refresh docs A", ["docs/a.md"]),
            opportunity("opp_docs_b", "Refresh docs B", ["docs/b.md"]),
        ],
        constitution=constitution(),
    )

    assert len(plans) == 1
    assert not plans[0].blocked
    assert plans[0].block_reason is None
    assert sorted(plans[0].opportunity_links.values_list("maintenance_opportunity_id", flat=True)) == [
        "opp_docs_a",
        "opp_docs_b",
    ]


@pytest.mark.django_db
def test_conservative_autonomy_mode_blocks_otherwise_allowed_plans():
    repository = demo_repository(autonomous_pr_add_on_enabled=True)
    policy = RepositoryAutomationPolicy.get_or_create_for_repository(repository)
    policy.autonomy_mode = RepositoryAutomationPolicy.AutonomyMode.CONSERVATIVE
    policy.save(update_fields=["autonomy_mode", "updated_at"])

    plans = plan_maintenance_prs(
        repository=repository,
        gardening_session_id="session_autonomy_gate",
        opportunities=[opportunity("opp_docs_a", "Refresh docs A", ["docs/a.md"])],
        constitution=constitution(),
    )

    assert len(plans) == 1
    assert plans[0].blocked
    assert plans[0].block_reason == CONSERVATIVE_AUTONOMY_PR_BLOCK_REASON


def demo_repository(*, autonomous_pr_add_on_enabled=True):
    organization = create_organization(900)
    Subscription.objects.create(
        organization=organization,
        autonomous_pr_add_on_enabled=autonomous_pr_add_on_enabled,
    )
    installation = create_installation(organization, 900)
    repository = create_repository(organization, installation, 900)
    RepositoryAutomationPolicy.objects.create(
        organization=organization,
        repository=repository,
        autonomy_mode=RepositoryAutomationPolicy.AutonomyMode.AUTONOMOUS,
    )
    return repository


def constitution():
    return {
        "schema_version": "1.0",
        "repository_id": "repo_demo",
        "commit_sha": "abc123",
        "completeness_score": 1,
        "protected_modules": [
            {
                "name": "billing",
                "paths": ["backend/apps/billing/**"],
                "reason": "Billing is protected.",
            }
        ],
        "never_touch": [
            {
                "path": "backend/apps/accounts/auth/**",
                "reason": "Auth requires human review.",
            }
        ],
        "allowed_fixes": {
            "autonomous": ["docs", "lint_format", "generated_refresh", "dependency_patch"],
            "assisted": ["tests", "refactoring"],
            "advisory": ["auth", "payments", "pricing", "permissions"],
        },
        "architecture_boundaries": [],
        "ignored_paths": [],
        "open_questions": [],
    }


def opportunity(
    maintenance_opportunity_id,
    title,
    affected_paths,
    *,
    category="docs",
    risk_tier="tier_1_autonomous",
    confidence=0.94,
):
    item = {
        "schema_version": "1.0",
        "maintenance_opportunity_id": maintenance_opportunity_id,
        "repository_id": "repo_demo",
        "analysis_snapshot_id": "snap_demo",
        "category": category,
        "risk_tier": risk_tier,
        "confidence": confidence,
        "title": title,
        "summary": f"{title} summary.",
        "affected_paths": affected_paths,
        "blocked_by": [],
        "expected_entropy_delta": -1.1,
        "required_checks": ["docs_review"],
        "evidence": [
            {
                "source_type": "file",
                "path": affected_paths[0],
                "section": "Overview",
                "line_start": 1,
                "line_end": 5,
                "summary": f"{title} evidence.",
            }
        ],
    }
    return copy.deepcopy(item)
