import copy
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from jsonschema import Draft202012Validator

from apps.analysis.fixtures import _schema_registry, _schema_path, _load_json
from apps.maintenance_prs.models import MaintenancePRPlanOpportunity
from apps.maintenance_prs.planner import (
    plan_maintenance_prs,
    serialize_maintenance_pr_plan,
)
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
def test_planner_blocks_low_confidence_protected_and_assisted_work():
    repository = demo_repository()
    opportunities = [
        opportunity("opp_low", "Low confidence", ["docs/low.md"], confidence=0.89),
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
    assert reasons["opp_low"] == "Confidence below 0.90 PR creation threshold."
    assert reasons["opp_protected"].startswith("Path backend/apps/billing/models.py matches protected module")
    assert reasons["opp_assisted"] == "Opportunity category requires assisted draft PR handling."
    assert all(plan.blocked for plan in plans)


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


def demo_repository():
    organization = create_organization(900)
    installation = create_installation(organization, 900)
    return create_repository(organization, installation, 900)


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
