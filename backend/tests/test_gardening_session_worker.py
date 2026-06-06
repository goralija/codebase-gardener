import copy

import pytest
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from apps.analysis.fixtures import load_first_report_fixture
from apps.accounts.models import CustomerOrganization
from apps.github_app.models import GitHubInstallation
from apps.repositories.models import ManagedRepository
from apps.sessions.models import GardeningSession
from apps.sessions.tasks import RetryableSessionError, run_gardening_session


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
    monkeypatch.setattr("apps.sessions.lifecycle.load_first_report_fixture", lambda: fixture)

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
def test_run_gardening_session_persists_failed_result_for_fixture_errors(
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
        "apps.sessions.lifecycle.load_first_report_fixture",
        lambda: (_ for _ in ()).throw(ImproperlyConfigured("bad fixture")),
    )

    result = run_gardening_session.apply(args=[str(session.id)], throw=False)

    session.refresh_from_db()
    assert result.failed()
    assert isinstance(result.result, ImproperlyConfigured)
    assert session.status == GardeningSession.Status.FAILED
    assert session.last_error == "bad fixture"
    assert session.result["repository_id"] == str(session.repository_id)
    assert session.result["status"] == "failed"
    assert session.result["phase_results"] == [
        {"phase": "observe", "status": "failed", "summary": "bad fixture"}
    ]
    assert session.result["errors"] == [{"phase": "observe", "message": "bad fixture"}]
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


def create_repository(identifier: int) -> ManagedRepository:
    organization = CustomerOrganization.objects.create(
        name=f"Organization {identifier}",
        github_account_id=1000 + identifier,
        github_login=f"org-{identifier}",
        github_account_type=CustomerOrganization.GitHubAccountType.ORGANIZATION,
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
