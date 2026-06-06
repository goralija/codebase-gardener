import copy
from types import SimpleNamespace

import pytest
from django.core.exceptions import ObjectDoesNotExist
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from apps.analysis.fixtures import load_first_report_fixture
from apps.analysis.runner import AnalysisRunError
from apps.accounts.models import CustomerOrganization
from apps.billing.models import Subscription
from apps.github_app.client import GitHubAPIError
from apps.github_app.models import GitHubInstallation
from apps.maintenance_prs.executor import PlanNotExecutableError
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.repositories.models import ManagedRepository
from apps.sessions.models import GardeningSession
from apps.sessions.tasks import RetryableSessionError, run_gardening_session


@pytest.fixture(autouse=True)
def _stub_real_analysis(monkeypatch):
    monkeypatch.setattr(
        "apps.sessions.tasks.run_repository_analysis",
        lambda repository: analysis_result(),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: load_first_report_fixture(),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.maybe_open_constitution_pr",
        lambda **_kwargs: {"created": False},
    )


@pytest.mark.django_db
def test_gardening_session_defaults_to_queued_state():
    session = GardeningSession.objects.create(
        repository=create_repository(1),
        trigger={"type": "manual", "actor": "user_demo"},
    )

    assert session.status == GardeningSession.Status.QUEUED
    assert session.trigger == {"type": "manual", "actor": "user_demo"}
    assert session.task_id == ""
    assert session.started_at is None
    assert session.finished_at is None
    assert session.result == {}
    assert session.last_error == ""
    assert session.retry_count == 0


@pytest.mark.django_db
def test_run_gardening_session_marks_session_completed(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    session = GardeningSession.objects.create(
        repository=create_repository(1),
        trigger={"type": "manual"},
    )

    result = run_gardening_session.delay(str(session.id)).get()

    session.refresh_from_db()
    assert result == {"session_id": str(session.id), "status": GardeningSession.Status.COMPLETED}
    assert session.status == GardeningSession.Status.COMPLETED
    assert session.task_id
    assert session.started_at is not None
    assert session.finished_at is not None
    assert session.result["gardening_session_id"] == str(session.id)
    assert session.result["repository_id"] == "repo_demo"
    assert session.result["trigger"] == {"type": "manual"}
    assert session.result["status"] == "completed"
    assert [phase["phase"] for phase in session.result["phase_results"]] == [
        "observe",
        "diagnose",
        "forecast",
        "plan",
        "execute",
        "learn",
    ]
    assert session.result["opportunities_selected"] == ["opp_demo_docs"]
    assert session.result["opportunities_deferred"] == []
    assert session.result["maintenance_pr_plans"] == ["pr_plan_demo_docs"]
    assert session.result["errors"] == []
    assert_gardening_session_result_contract(session.result)
    assert session.last_error == ""
    assert session.retry_count == 0


@pytest.mark.django_db
def test_run_gardening_session_uses_analysis_report(settings, monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "first_scan"},
    )
    report = copy.deepcopy(load_first_report_fixture())
    report["repository_constitution"]["repository_id"] = str(repository.id)
    report["maintenance_opportunities"] = []
    report["maintenance_pr_plans"] = []

    monkeypatch.setattr(
        "apps.sessions.tasks.run_repository_analysis",
        lambda repository: analysis_result(),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: report,
    )

    run_gardening_session.delay(str(session.id)).get()

    session.refresh_from_db()
    assert session.status == GardeningSession.Status.COMPLETED
    assert session.result["repository_id"] == str(repository.id)
    assert session.result["opportunities_selected"] == []


@pytest.mark.django_db
def test_run_gardening_session_offers_constitution_pr_from_analysis_artifacts(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "first_scan"},
    )
    artifacts = {
        "constitution": {
            "open_questions": [
                {
                    "severity": "blocking",
                    "question": "No repository constitution (GARDENER.md) found.",
                }
            ]
        }
    }
    calls = []

    monkeypatch.setattr(
        "apps.sessions.tasks.run_repository_analysis",
        lambda repository: SimpleNamespace(analysis=object(), artifacts=artifacts),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.maybe_open_constitution_pr",
        lambda **kwargs: calls.append(kwargs) or {"created": True},
    )

    run_gardening_session.delay(str(session.id)).get()

    assert calls == [{"repository": repository, "artifacts": artifacts}]


@pytest.mark.django_db
def test_run_gardening_session_plans_and_executes_first_report_opportunities(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "first_scan"},
    )
    report = first_report_for_repository(
        repository,
        opportunities=[
            opportunity("opp_docs", "Refresh docs", ["docs/api.md"]),
            opportunity(
                "opp_tests",
                "Add tenant tests",
                ["tenants/test_gap.py"],
                category="tests",
                risk_tier="tier_2_assisted",
                confidence=0.94,
            ),
        ],
    )
    executed: list[str] = []

    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: report,
    )
    monkeypatch.setattr(
        "apps.maintenance_prs.executor.execute_maintenance_pr_plan",
        lambda plan: executed.append(str(plan.id)),
    )

    run_gardening_session.delay(str(session.id)).get()

    session.refresh_from_db()
    plans = list(MaintenancePRPlan.objects.for_session(str(session.id)).order_by("title"))
    assert len(plans) == 2

    unblocked = [plan for plan in plans if not plan.blocked]
    blocked = [plan for plan in plans if plan.blocked]
    assert len(unblocked) == 1
    assert len(blocked) == 1
    assert unblocked[0].approval_status == MaintenancePRPlan.ApprovalStatus.APPROVED
    assert blocked[0].approval_status == MaintenancePRPlan.ApprovalStatus.PENDING
    assert blocked[0].block_reason == "Opportunity category requires assisted draft PR handling."
    assert executed == [str(unblocked[0].id)]
    assert session.result["opportunities_selected"] == ["opp_docs"]
    assert session.result["opportunities_deferred"] == [
        {
            "maintenance_opportunity_id": "opp_tests",
            "reason": "Opportunity category requires assisted draft PR handling.",
        }
    ]
    assert session.result["maintenance_pr_plans"] == [str(unblocked[0].id)]
    assert session.result["errors"] == []
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_plans_and_executes_real_opportunities(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "manual"},
    )
    opportunities = [
        worker_opportunity(
            "opp_lint",
            "Format generated client",
            ["src/client.py"],
            "lint_format",
            0.98,
        ),
        worker_opportunity("opp_docs", "Refresh README", ["README.md"], "docs", 0.94),
        worker_opportunity(
            "opp_generated",
            "Refresh generated schema",
            ["schema/openapi.json"],
            "generated_refresh",
            0.97,
        ),
        worker_opportunity(
            "opp_dependency",
            "Patch dependency",
            ["requirements.txt"],
            "dependency_patch",
            0.96,
        ),
    ]
    artifacts = {
        "constitution": worker_constitution(repository),
        "opportunities": opportunities,
    }
    report = report_for_repository(repository, opportunities)
    executed: list[str] = []

    monkeypatch.setattr(
        "apps.sessions.tasks.run_repository_analysis",
        lambda repository: SimpleNamespace(analysis=object(), artifacts=artifacts),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: report,
    )

    def execute(plan):
        executed.append(str(plan.id))
        MaintenancePRPlan.objects.filter(id=plan.id).update(
            execution_status=MaintenancePRPlan.ExecutionStatus.SUCCEEDED
        )

    monkeypatch.setattr("apps.maintenance_prs.executor.execute_maintenance_pr_plan", execute)

    run_gardening_session.delay(str(session.id)).get()

    session.refresh_from_db()
    plans = list(
        MaintenancePRPlan.objects.for_session(str(session.id)).order_by("created_at", "id")
    )
    assert len(plans) == 4
    approved = [plan for plan in plans if plan.approval_status == "approved"]
    assert len(approved) == 1
    assert approved[0].category == "docs"
    assert len(executed) == 1
    assert set(executed) == {str(plan.id) for plan in approved}
    assert session.result["maintenance_pr_plans"] == executed
    assert session.result["opportunities_selected"] == ["opp_docs"]
    assert session.result["opportunities_deferred"] == [
        {
            "maintenance_opportunity_id": "opp_lint",
            "reason": "Plan is pending approval for autonomous execution.",
        },
        {
            "maintenance_opportunity_id": "opp_generated",
            "reason": "Plan is pending approval for autonomous execution.",
        },
        {
            "maintenance_opportunity_id": "opp_dependency",
            "reason": "Plan is pending approval for autonomous execution.",
        },
    ]
    assert session.result["errors"] == []


@pytest.mark.django_db
def test_run_gardening_session_defers_safe_docs_plans_over_auto_approval_cap(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "manual"},
    )
    opportunities = [
        worker_opportunity(
            f"opp_docs_{index}",
            f"Refresh docs {index}",
            [f"docs/{index}.md"],
            "docs",
            0.94,
        )
        for index in range(10)
    ]
    artifacts = {
        "constitution": worker_constitution(repository),
        "opportunities": opportunities,
    }
    report = report_for_repository(repository, opportunities)
    executed: list[str] = []

    monkeypatch.setattr(
        "apps.sessions.tasks.run_repository_analysis",
        lambda repository: SimpleNamespace(analysis=object(), artifacts=artifacts),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: report,
    )

    def execute(plan):
        executed.append(str(plan.id))
        MaintenancePRPlan.objects.filter(id=plan.id).update(
            execution_status=MaintenancePRPlan.ExecutionStatus.SUCCEEDED
        )

    monkeypatch.setattr("apps.maintenance_prs.executor.execute_maintenance_pr_plan", execute)

    run_gardening_session.delay(str(session.id)).get()

    session.refresh_from_db()
    plans = list(
        MaintenancePRPlan.objects.for_session(str(session.id)).order_by("created_at", "id")
    )
    approved = [plan for plan in plans if plan.approval_status == "approved"]
    pending = [plan for plan in plans if plan.approval_status == "pending"]
    assert len(plans) == 4
    assert len(approved) == 3
    assert len(pending) == 1
    assert session.result["maintenance_pr_plans"] == executed
    assert session.result["opportunities_selected"] == [
        f"opp_docs_{index}" for index in range(9)
    ]
    assert session.result["opportunities_deferred"] == [
        {
            "maintenance_opportunity_id": "opp_docs_9",
            "reason": "Plan is pending approval for autonomous execution.",
        }
    ]


@pytest.mark.django_db
def test_run_gardening_session_does_not_approve_blocked_protected_or_low_confidence(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "manual"},
    )
    opportunities = [
        worker_opportunity(
            "opp_low",
            "Refresh low confidence docs",
            ["docs/low.md"],
            "docs",
            0.50,
        ),
        worker_opportunity(
            "opp_protected",
            "Refresh secret docs",
            ["secret/guide.md"],
            "docs",
            0.94,
        ),
    ]
    artifacts = {
        "constitution": worker_constitution(
            repository,
            never_touch=[{"path": "secret/**", "reason": "Secrets stay human-reviewed."}],
        ),
        "opportunities": opportunities,
    }
    report = report_for_repository(repository, opportunities)
    executed: list[str] = []

    monkeypatch.setattr(
        "apps.sessions.tasks.run_repository_analysis",
        lambda repository: SimpleNamespace(analysis=object(), artifacts=artifacts),
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: report,
    )
    monkeypatch.setattr(
        "apps.maintenance_prs.executor.execute_maintenance_pr_plan",
        lambda plan: executed.append(str(plan.id)),
    )

    run_gardening_session.delay(str(session.id)).get()

    session.refresh_from_db()
    plans = list(MaintenancePRPlan.objects.for_session(str(session.id)))
    assert len(plans) == 2
    assert all(plan.blocked for plan in plans)
    assert all(plan.approval_status == "pending" for plan in plans)
    assert executed == []
    assert session.result["maintenance_pr_plans"] == []
    assert sorted(
        item["maintenance_opportunity_id"]
        for item in session.result["opportunities_deferred"]
    ) == ["opp_low", "opp_protected"]


@pytest.mark.django_db
def test_run_gardening_session_planning_is_idempotent_per_session_opportunity(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "first_scan"},
    )
    report = first_report_for_repository(
        repository,
        opportunities=[opportunity("opp_docs", "Refresh docs", ["docs/api.md"])],
    )

    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: report,
    )
    monkeypatch.setattr(
        "apps.maintenance_prs.executor.execute_maintenance_pr_plan",
        lambda _plan: None,
    )

    run_gardening_session.delay(str(session.id)).get()
    run_gardening_session.delay(str(session.id)).get()

    session.refresh_from_db()
    assert MaintenancePRPlan.objects.for_session(str(session.id)).count() == 1
    assert session.result["opportunities_selected"] == ["opp_docs"]


@pytest.mark.django_db
def test_run_gardening_session_marks_session_failed_with_partial_result(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    session = GardeningSession.objects.create(
        repository=create_repository(1),
        trigger={"type": "manual", "simulate": "failure", "fail_phase": "forecast"},
    )

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.failed()
    assert session.status == GardeningSession.Status.FAILED
    assert session.finished_at is not None
    assert session.last_error == "Simulated forecast phase failure."
    assert session.result["status"] == "failed"
    assert [phase["phase"] for phase in session.result["phase_results"]] == [
        "observe",
        "diagnose",
        "forecast",
    ]
    assert session.result["phase_results"][-1]["status"] == "failed"
    assert session.result["errors"] == [
        {"phase": "forecast", "message": "Simulated forecast phase failure."}
    ]
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_defers_fixture_opportunities_without_ready_plan(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    fixture = copy.deepcopy(load_first_report_fixture())
    fixture["maintenance_opportunities"].append(
        {
            **fixture["maintenance_opportunities"][0],
            "maintenance_opportunity_id": "opp_blocked",
            "blocked_by": ["opp_demo_docs"],
        }
    )
    fixture["maintenance_opportunities"].append(
        {
            **fixture["maintenance_opportunities"][0],
            "maintenance_opportunity_id": "opp_missing_plan",
            "blocked_by": [],
        }
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.storage_service.load_first_report",
        lambda _analysis: fixture,
    )

    session = GardeningSession.objects.create(
        repository=create_repository(1),
        trigger={"type": "manual"},
    )

    run_gardening_session.delay(str(session.id)).get()

    session.refresh_from_db()
    assert session.result["opportunities_selected"] == ["opp_demo_docs"]
    assert session.result["maintenance_pr_plans"] == ["pr_plan_demo_docs"]
    assert session.result["opportunities_deferred"] == [
        {
            "maintenance_opportunity_id": "opp_blocked",
            "reason": "Blocked by another opportunity.",
        },
        {
            "maintenance_opportunity_id": "opp_missing_plan",
            "reason": "No matching fixture PR plan.",
        },
    ]
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_marks_failed_after_retry_exhaustion(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    session = GardeningSession.objects.create(
        repository=create_repository(1),
        trigger={"type": "manual", "simulate": "retryable_error"},
    )

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.failed()
    assert isinstance(result.result, RetryableSessionError)
    assert session.status == GardeningSession.Status.FAILED
    assert session.retry_count == 3
    assert session.finished_at is not None
    assert session.last_error == "Simulated retryable session error."
    assert session.result["status"] == "failed"
    assert session.result["phase_results"] == [
        {
            "phase": "observe",
            "status": "failed",
            "summary": "Simulated retryable session error.",
        }
    ]
    assert session.result["errors"] == [
        {"phase": "observe", "message": "Simulated retryable session error."}
    ]
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_retries_github_execute_errors(settings, monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    session = GardeningSession.objects.create(
        repository=create_repository(1),
        trigger={"type": "manual"},
    )

    def fail_github(_session):
        raise GitHubAPIError("rate limited", status_code=429)

    monkeypatch.setattr("apps.sessions.tasks.execute_session_pr_plans", fail_github)

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.failed()
    assert isinstance(result.result, GitHubAPIError)
    assert session.status == GardeningSession.Status.FAILED
    assert session.retry_count == 3
    assert session.last_error == "rate limited"
    assert session.result["phase_results"][-1] == {
        "phase": "execute",
        "status": "failed",
        "summary": "rate limited",
    }
    assert session.result["errors"] == [{"phase": "execute", "message": "rate limited"}]
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_marks_non_retryable_github_error_failed(settings, monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    session = GardeningSession.objects.create(
        repository=create_repository(1),
        trigger={"type": "manual"},
    )

    def fail_github(_session):
        raise GitHubAPIError("bad request", status_code=422)

    monkeypatch.setattr("apps.sessions.tasks.execute_session_pr_plans", fail_github)

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.failed()
    assert isinstance(result.result, GitHubAPIError)
    assert session.status == GardeningSession.Status.FAILED
    assert session.retry_count == 0
    assert session.last_error == "bad request"
    assert session.result["errors"] == [{"phase": "execute", "message": "bad request"}]
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_reports_pr_policy_failure_and_continues(settings, monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "manual"},
    )
    MaintenancePRPlan.objects.create(
        repository=repository,
        gardening_session_id=str(session.id),
        branch_name="gardener/docs-refresh",
        title="Refresh docs",
        risk_tier="tier_1_autonomous",
        confidence=0.94,
        approval_status=MaintenancePRPlan.ApprovalStatus.APPROVED,
    )
    second = MaintenancePRPlan.objects.create(
        repository=repository,
        gardening_session_id=str(session.id),
        branch_name="gardener/docs-other",
        title="Refresh other docs",
        risk_tier="tier_1_autonomous",
        confidence=0.94,
        approval_status=MaintenancePRPlan.ApprovalStatus.APPROVED,
    )

    def execute_or_fail(plan):
        if plan.branch_name == "gardener/docs-refresh":
            raise PlanNotExecutableError("Plan became unsafe.")

    monkeypatch.setattr("apps.maintenance_prs.executor.execute_maintenance_pr_plan", execute_or_fail)

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.successful()
    assert session.status == GardeningSession.Status.COMPLETED
    assert session.last_error == ""
    assert session.result["maintenance_pr_plans"] == [str(second.id)]
    assert session.result["errors"] == [
        {
            "phase": "execute",
            "maintenance_pr_plan_id": str(
                MaintenancePRPlan.objects.get(branch_name="gardener/docs-refresh").id
            ),
            "message": "Plan became unsafe.",
        }
    ]
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_reports_permanent_github_plan_failure_and_continues(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "manual"},
    )
    failed = MaintenancePRPlan.objects.create(
        repository=repository,
        gardening_session_id=str(session.id),
        branch_name="gardener/docs-refresh",
        title="Refresh docs",
        risk_tier="tier_1_autonomous",
        confidence=0.94,
        approval_status=MaintenancePRPlan.ApprovalStatus.APPROVED,
    )
    succeeded = MaintenancePRPlan.objects.create(
        repository=repository,
        gardening_session_id=str(session.id),
        branch_name="gardener/docs-other",
        title="Refresh other docs",
        risk_tier="tier_1_autonomous",
        confidence=0.94,
        approval_status=MaintenancePRPlan.ApprovalStatus.APPROVED,
    )

    def execute_or_fail(plan):
        if plan.id == failed.id:
            raise GitHubAPIError("bad request", status_code=422)

    monkeypatch.setattr("apps.maintenance_prs.executor.execute_maintenance_pr_plan", execute_or_fail)

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.successful()
    assert session.status == GardeningSession.Status.COMPLETED
    assert session.last_error == ""
    assert session.result["maintenance_pr_plans"] == [str(succeeded.id)]
    assert session.result["errors"] == [
        {
            "phase": "execute",
            "maintenance_pr_plan_id": str(failed.id),
            "message": "bad request",
        }
    ]
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_retries_retryable_github_plan_failure(settings, monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    repository = create_repository(1)
    session = GardeningSession.objects.create(
        repository=repository,
        trigger={"type": "manual"},
    )
    MaintenancePRPlan.objects.create(
        repository=repository,
        gardening_session_id=str(session.id),
        branch_name="gardener/docs-refresh",
        title="Refresh docs",
        risk_tier="tier_1_autonomous",
        confidence=0.94,
        approval_status=MaintenancePRPlan.ApprovalStatus.APPROVED,
    )

    def fail_retryable(_plan):
        raise GitHubAPIError("rate limited", status_code=429)

    monkeypatch.setattr("apps.maintenance_prs.executor.execute_maintenance_pr_plan", fail_retryable)

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.failed()
    assert isinstance(result.result, GitHubAPIError)
    assert session.status == GardeningSession.Status.FAILED
    assert session.retry_count == 3
    assert session.last_error == "rate limited"


@pytest.mark.django_db
def test_run_gardening_session_persists_failed_result_for_analysis_errors(
    settings,
    monkeypatch,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    session = GardeningSession.objects.create(
        repository=create_repository(1),
        trigger={"type": "manual"},
    )
    monkeypatch.setattr(
        "apps.sessions.tasks.run_repository_analysis",
        lambda repository: (_ for _ in ()).throw(
            AnalysisRunError("diagnose", "Repowise failed")
        ),
    )

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.failed()
    assert isinstance(result.result, AnalysisRunError)
    assert session.status == GardeningSession.Status.FAILED
    assert session.last_error == "Repowise failed"
    assert session.result["repository_id"] == str(session.repository_id)
    assert session.result["status"] == "failed"
    assert session.result["phase_results"] == [
        {
            "phase": "observe",
            "status": "completed",
            "summary": "Loaded shared fixture repository state.",
        },
        {"phase": "diagnose", "status": "failed", "summary": "Repowise failed"},
    ]
    assert session.result["errors"] == [{"phase": "diagnose", "message": "Repowise failed"}]
    assert_gardening_session_result_contract(session.result)


@pytest.mark.django_db
def test_run_gardening_session_missing_session_fails_without_state(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False

    result = run_gardening_session.apply(args=["00000000-0000-0000-0000-000000000000"], throw=False)

    assert result.failed()
    assert isinstance(result.result, ObjectDoesNotExist)
    assert GardeningSession.objects.count() == 0


def assert_gardening_session_result_contract(payload: dict):
    schema = load_fixture_schema("gardening_session_result.schema.json")
    validator = Draft202012Validator(schema, registry=fixture_schema_registry())
    errors = sorted(validator.iter_errors(payload), key=lambda error: error.json_path)
    assert errors == []


def fixture_schema_registry() -> Registry:
    resources = []
    schema_dir = repo_root() / "fixtures" / "schemas"
    for schema_path in schema_dir.glob("*.schema.json"):
        schema = load_fixture_schema(schema_path.name)
        if "$id" in schema:
            resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def load_fixture_schema(name: str) -> dict:
    import json

    return json.loads((repo_root() / "fixtures" / "schemas" / name).read_text(encoding="utf-8"))


def repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]


def analysis_result():
    return SimpleNamespace(analysis=object(), artifacts={"constitution": {"open_questions": []}})


def first_report_for_repository(repository: ManagedRepository, *, opportunities: list[dict]):
    report = copy.deepcopy(load_first_report_fixture())
    report["repository_constitution"] = constitution_for_repository(repository)
    report["maintenance_opportunities"] = copy.deepcopy(opportunities)
    report["maintenance_pr_plans"] = []
    return report


def report_for_repository(repository: ManagedRepository, opportunities: list[dict]) -> dict:
    return first_report_for_repository(repository, opportunities=opportunities)


def constitution_for_repository(
    repository: ManagedRepository,
    *,
    never_touch: list[dict] | None = None,
) -> dict:
    never_touch_rules = never_touch or [
        {
            "path": "**/.env*",
            "reason": "Secrets require human handling.",
        }
    ]
    return {
        "schema_version": "1.0",
        "repository_id": str(repository.id),
        "commit_sha": "abc123",
        "completeness_score": 1.0,
        "protected_modules": [
            {
                "name": "billing",
                "paths": ["billing/**"],
                "reason": "Billing is protected.",
            }
        ],
        "never_touch": never_touch_rules,
        "allowed_fixes": {
            "autonomous": ["docs", "lint_format", "generated_refresh", "dependency_patch"],
            "assisted": ["tests", "refactoring", "complexity_reduction"],
            "advisory": ["auth", "payments", "pricing", "permissions"],
        },
        "architecture_boundaries": [],
        "ignored_paths": [],
        "open_questions": [],
    }


def worker_constitution(
    repository: ManagedRepository,
    *,
    never_touch: list[dict] | None = None,
) -> dict:
    return constitution_for_repository(repository, never_touch=never_touch or [])


def opportunity(
    maintenance_opportunity_id: str,
    title: str,
    affected_paths: list[str],
    *,
    category: str = "docs",
    risk_tier: str = "tier_1_autonomous",
    confidence: float = 0.94,
    expected_entropy_delta: float = -1.1,
    required_checks: list[str] | None = None,
):
    checks = required_checks or ["docs_review"]
    return {
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
        "expected_entropy_delta": expected_entropy_delta,
        "required_checks": checks,
        "evidence": [
            {
                "source_type": "file",
                "path": affected_paths[0],
                "line_start": 1,
                "line_end": 5,
                "summary": f"{title} evidence.",
            }
        ],
    }


def worker_opportunity(
    maintenance_opportunity_id: str,
    title: str,
    affected_paths: list[str],
    category: str,
    confidence: float,
) -> dict:
    return opportunity(
        maintenance_opportunity_id,
        title,
        affected_paths,
        category=category,
        confidence=confidence,
        expected_entropy_delta=-1.0,
        required_checks=["backend-test"],
    )


def create_repository(identifier: int) -> ManagedRepository:
    organization = CustomerOrganization.objects.create(
        name=f"Organization {identifier}",
        github_account_id=1000 + identifier,
        github_login=f"org-{identifier}",
        github_account_type=CustomerOrganization.GitHubAccountType.ORGANIZATION,
    )
    Subscription.objects.create(
        organization=organization,
        autonomous_pr_add_on_enabled=True,
    )
    installation = GitHubInstallation.objects.create(
        organization=organization,
        github_installation_id=2000 + identifier,
        github_account_id=organization.github_account_id,
        github_account_login=organization.github_login,
        github_account_type=GitHubInstallation.GitHubAccountType.ORGANIZATION,
        repository_selection=GitHubInstallation.RepositorySelection.SELECTED,
        permissions={"metadata": "read", "contents": "read"},
        events=["installation", "repository"],
    )
    return ManagedRepository.objects.create(
        organization=organization,
        github_installation=installation,
        github_repository_id=3000 + identifier,
        name=f"repo-{identifier}",
        full_name=f"org-{identifier}/repo-{identifier}",
        owner_login=f"org-{identifier}",
        private=True,
        default_branch="main",
        html_url=f"https://github.com/org-{identifier}/repo-{identifier}",
    )
