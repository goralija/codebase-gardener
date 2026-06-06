import httpx
import pytest
from base64 import b64encode
from django.utils import timezone

from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError
from apps.maintenance_prs.executor import (
    PlanNotExecutableError,
    execute_maintenance_pr_plan,
)
from apps.maintenance_prs.models import MaintenancePRPlan
from tests.test_product_models import (
    create_installation,
    create_organization,
    create_repository,
)


class FakeGitHubClient:
    def __init__(
        self,
        *,
        create_branch_error=None,
        fail_at=None,
        create_pr_error=None,
        get_file_contents_error=None,
        existing_pr=None,
        marker_sha=None,
        marker_content=None,
        pr_response=None,
    ):
        self.calls = []
        self.create_branch_error = create_branch_error
        self.fail_at = fail_at
        self.create_pr_error = create_pr_error
        self.get_file_contents_error = get_file_contents_error
        self.existing_pr = existing_pr
        self.marker_sha = marker_sha
        self.marker_content = marker_content
        self.pr_response = pr_response

    def create_installation_token(self, installation_id):
        self.calls.append(("create_installation_token", installation_id))
        return "ghs_token"

    def get_branch_ref(self, owner, repo, branch, *, token):
        self.calls.append(("get_branch_ref", owner, repo, branch))
        self._maybe_fail("get_branch_ref")
        return "base_sha"

    def create_branch_ref(self, owner, repo, *, branch, sha, token):
        self.calls.append(("create_branch_ref", owner, repo, branch, sha))
        if self.create_branch_error is not None:
            raise self.create_branch_error
        self._maybe_fail("create_branch_ref")
        return {"ref": f"refs/heads/{branch}"}

    def get_file_sha(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_sha", owner, repo, path, branch))
        self._maybe_fail("get_file_sha")
        return self.marker_sha

    def get_file_contents(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_contents", owner, repo, path, branch))
        if self.get_file_contents_error is not None:
            raise self.get_file_contents_error
        self._maybe_fail("get_file_contents")
        return self.marker_content or ""

    def put_file_contents(self, owner, repo, path, *, message, content, branch, token, sha=None):
        self.calls.append(("put_file_contents", owner, repo, path, branch, sha))
        self._maybe_fail("put_file_contents")
        return {"commit": {"sha": "commit_sha"}}

    def create_pull_request(self, owner, repo, *, title, head, base, body, token):
        self.calls.append(("create_pull_request", owner, repo, head, base))
        if self.create_pr_error is not None:
            raise self.create_pr_error
        self._maybe_fail("create_pull_request")
        if self.pr_response is not None:
            return self.pr_response
        return {"number": 42, "html_url": "https://github.com/org-1/repo-1/pull/42"}

    def find_pull_request(self, owner, repo, *, head, base, token):
        self.calls.append(("find_pull_request", owner, repo, head, base))
        return self.existing_pr

    def _maybe_fail(self, name):
        if self.fail_at == name:
            raise GitHubAPIError("GitHub request failed.", status_code=500)


def _names(client):
    return [call[0] for call in client.calls]


def make_repository(identifier=1):
    organization = create_organization(identifier)
    installation = create_installation(organization, identifier)
    return create_repository(organization, installation, identifier)


def make_plan(repository=None, **overrides):
    repository = repository or make_repository()
    defaults = dict(
        repository=repository,
        gardening_session_id="session_exec",
        branch_name="gardener/docs-refresh",
        title="Refresh docs",
        risk_tier="tier_1_autonomous",
        confidence=0.94,
        changed_paths=["docs/api.md"],
        pr_body_sections={
            "goal": "Point to current truth.",
            "evidence": "Docs were stale.",
            "entropy_impact": "-2.1 entropy.",
            "verification": "Run docs review.",
            "roi_impact": "0.5 hours saved.",
        },
        required_checks=["docs_review"],
        approval_status=MaintenancePRPlan.ApprovalStatus.APPROVED,
    )
    defaults.update(overrides)
    return MaintenancePRPlan.objects.create(**defaults)


@pytest.mark.django_db
def test_execute_happy_path_creates_branch_and_pr():
    plan = make_plan()
    client = FakeGitHubClient()

    result = execute_maintenance_pr_plan(plan, client=client)

    assert _names(client) == [
        "create_installation_token",
        "get_branch_ref",
        "create_branch_ref",
        "get_file_sha",
        "put_file_contents",
        "create_pull_request",
    ]
    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    assert plan.created_pr_number == 42
    assert plan.created_pr_url == "https://github.com/org-1/repo-1/pull/42"
    assert plan.created_branch_ref == "refs/heads/gardener/docs-refresh"
    assert plan.execution_error == ""
    assert result["created_pr_number"] == 42

    put_call = next(c for c in client.calls if c[0] == "put_file_contents")
    assert put_call[3] == ".gardener/plans/gardener-docs-refresh.md"


@pytest.mark.django_db
def test_execute_tolerates_existing_branch():
    plan = make_plan()
    client = FakeGitHubClient(
        create_branch_error=GitHubAPIError("exists", status_code=422),
        marker_content=f"<!-- gardener-maintenance-pr-plan-id: {plan.id} -->",
    )

    execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    assert "create_pull_request" in _names(client)


@pytest.mark.django_db
def test_existing_branch_without_matching_marker_fails():
    plan = make_plan()
    client = FakeGitHubClient(
        create_branch_error=GitHubAPIError("exists", status_code=422),
        marker_content="<!-- gardener-maintenance-pr-plan-id: other -->",
    )

    with pytest.raises(PlanNotExecutableError):
        execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.FAILED
    assert "put_file_contents" not in _names(client)


@pytest.mark.django_db
def test_existing_branch_missing_marker_fails_as_ownership_error():
    plan = make_plan()
    client = FakeGitHubClient(
        create_branch_error=GitHubAPIError("exists", status_code=422),
        get_file_contents_error=GitHubAPIError("not found", status_code=404),
    )

    with pytest.raises(PlanNotExecutableError):
        execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.FAILED
    assert "does not belong" in plan.execution_error
    assert "put_file_contents" not in _names(client)


@pytest.mark.django_db
def test_execute_records_failure_and_reraises():
    plan = make_plan()
    client = FakeGitHubClient(fail_at="create_pull_request")

    with pytest.raises(GitHubAPIError):
        execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.FAILED
    assert plan.execution_error
    assert plan.created_pr_number is None


@pytest.mark.django_db
def test_non_422_branch_error_fails():
    plan = make_plan()
    client = FakeGitHubClient(
        create_branch_error=GitHubAPIError("boom", status_code=500)
    )

    with pytest.raises(GitHubAPIError):
        execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.FAILED
    assert "put_file_contents" not in _names(client)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"approval_status": MaintenancePRPlan.ApprovalStatus.PENDING},
        {
            "blocked": True,
            "block_reason": "Conflicts with protected path.",
        },
        {"execution_status": MaintenancePRPlan.ExecutionStatus.SUCCEEDED},
        {"execution_status": MaintenancePRPlan.ExecutionStatus.RUNNING},
        {"risk_tier": "tier_2_assisted"},
    ],
)
def test_gate_blocks_non_executable_plans(overrides):
    plan = make_plan(**overrides)
    client = FakeGitHubClient()

    with pytest.raises(PlanNotExecutableError):
        execute_maintenance_pr_plan(plan, client=client)

    assert client.calls == []


@pytest.mark.django_db
def test_claim_blocks_if_plan_already_running_in_db():
    plan = make_plan()
    MaintenancePRPlan.objects.filter(id=plan.id).update(
        execution_status=MaintenancePRPlan.ExecutionStatus.RUNNING
    )
    plan.execution_status = MaintenancePRPlan.ExecutionStatus.PENDING
    client = FakeGitHubClient()

    with pytest.raises(PlanNotExecutableError):
        execute_maintenance_pr_plan(plan, client=client)

    assert client.calls == []


@pytest.mark.django_db
def test_stale_running_plan_can_be_reclaimed():
    plan = make_plan(execution_status=MaintenancePRPlan.ExecutionStatus.RUNNING)
    MaintenancePRPlan.objects.filter(id=plan.id).update(
        updated_at=timezone.now() - timezone.timedelta(minutes=31)
    )
    plan.refresh_from_db()
    client = FakeGitHubClient()

    execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    assert "create_pull_request" in _names(client)


@pytest.mark.django_db
def test_claim_blocks_if_repository_becomes_inactive_in_db():
    plan = make_plan()
    repository = plan.repository
    repository.unselected_at = timezone.now()
    repository.save(update_fields=["unselected_at", "updated_at"])
    repository.unselected_at = None
    plan.repository = repository
    client = FakeGitHubClient()

    with pytest.raises(PlanNotExecutableError):
        execute_maintenance_pr_plan(plan, client=client)

    assert client.calls == []


@pytest.mark.django_db
def test_low_confidence_plan_blocked():
    plan = make_plan(confidence=0.80)
    client = FakeGitHubClient()

    with pytest.raises(PlanNotExecutableError):
        execute_maintenance_pr_plan(plan, client=client)

    assert client.calls == []
    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.PENDING


@pytest.mark.django_db
def test_plan_confidence_threshold_blocks_stricter_policy():
    plan = make_plan(confidence=0.92, confidence_threshold=0.95)
    client = FakeGitHubClient()

    with pytest.raises(PlanNotExecutableError):
        execute_maintenance_pr_plan(plan, client=client)

    assert client.calls == []
    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.PENDING


@pytest.mark.django_db
def test_inactive_repository_blocked():
    repository = make_repository()
    repository.unselected_at = timezone.now()
    repository.save(update_fields=["unselected_at", "updated_at"])
    plan = make_plan(repository=repository)
    client = FakeGitHubClient()

    with pytest.raises(PlanNotExecutableError):
        execute_maintenance_pr_plan(plan, client=client)

    assert client.calls == []


@pytest.mark.django_db
def test_existing_pr_tolerated_on_rerun():
    plan = make_plan()
    client = FakeGitHubClient(
        create_pr_error=GitHubAPIError("exists", status_code=422),
        existing_pr={"number": 99, "html_url": "https://github.com/org-1/repo-1/pull/99"},
    )

    execute_maintenance_pr_plan(plan, client=client)

    assert "find_pull_request" in _names(client)
    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    assert plan.created_pr_number == 99


@pytest.mark.django_db
def test_existing_marker_file_is_updated_with_sha():
    plan = make_plan()
    client = FakeGitHubClient(marker_sha="existing_sha")

    execute_maintenance_pr_plan(plan, client=client)

    put_call = next(c for c in client.calls if c[0] == "put_file_contents")
    assert put_call[5] == "existing_sha"


@pytest.mark.django_db
def test_non_github_error_marks_failed():
    plan = make_plan()

    class BrokenClient(FakeGitHubClient):
        def create_installation_token(self, installation_id):
            raise RuntimeError("token boom")

    with pytest.raises(RuntimeError):
        execute_maintenance_pr_plan(plan, client=BrokenClient())

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.FAILED
    assert plan.execution_error


@pytest.mark.django_db
def test_malformed_pr_response_marks_failed():
    plan = make_plan()
    client = FakeGitHubClient(pr_response={"html_url": "https://github.com/org-1/repo-1/pull/x"})

    with pytest.raises(GitHubAPIError):
        execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.FAILED
    assert plan.created_pr_number is None
    assert "valid number" in plan.execution_error


@pytest.mark.django_db
def test_audit_event_written_on_success():
    plan = make_plan()
    execute_maintenance_pr_plan(plan, client=FakeGitHubClient())

    event = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.MAINTENANCE_PR_CREATED
    )
    assert event.repository_id == plan.repository_id
    assert event.organization_id == plan.repository.organization_id
    assert event.source == "gardening_worker"
    assert event.metadata["pr_number"] == 42
    assert event.metadata["maintenance_pr_plan_id"] == str(plan.id)


@pytest.mark.django_db
def test_audit_event_written_on_failure():
    plan = make_plan()
    client = FakeGitHubClient(fail_at="create_pull_request")

    with pytest.raises(GitHubAPIError):
        execute_maintenance_pr_plan(plan, client=client)

    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.MAINTENANCE_PR_CREATION_FAILED
    ).exists()


@pytest.mark.django_db
def test_executable_queryset_filters():
    repository = make_repository()
    approved = make_plan(repository=repository)
    failed = make_plan(
        repository=repository,
        branch_name="gardener/failed",
        execution_status=MaintenancePRPlan.ExecutionStatus.FAILED,
    )
    make_plan(
        repository=repository,
        branch_name="gardener/pending",
        approval_status=MaintenancePRPlan.ApprovalStatus.PENDING,
    )
    make_plan(
        repository=repository,
        branch_name="gardener/running",
        execution_status=MaintenancePRPlan.ExecutionStatus.RUNNING,
    )
    make_plan(
        repository=repository,
        branch_name="gardener/low-confidence",
        confidence=0.80,
    )
    make_plan(
        repository=repository,
        branch_name="gardener/strict-threshold",
        confidence=0.92,
        confidence_threshold=0.95,
    )
    make_plan(
        repository=repository,
        branch_name="gardener/tier-2",
        risk_tier="tier_2_assisted",
    )
    inactive_repository = make_repository(2)
    inactive_repository.unselected_at = timezone.now()
    inactive_repository.save(update_fields=["unselected_at", "updated_at"])
    make_plan(repository=inactive_repository, branch_name="gardener/inactive")

    executable = list(
        MaintenancePRPlan.objects.for_session("session_exec").executable()
    )
    assert executable == [approved, failed]


@pytest.mark.django_db
def test_to_execution_status_shape():
    plan = make_plan()
    status = plan.to_execution_status()
    assert status["approval_status"] == "approved"
    assert status["execution_status"] == "pending"
    assert status["created_pr_number"] is None


def test_client_write_methods_use_json_body(monkeypatch):
    from apps.github_app.client import GitHubAppClient

    requests = []
    responses = [
        httpx.Response(201, json={"ref": "refs/heads/gardener/x"}),
        httpx.Response(200, json={"sha": "existing_sha"}),
        httpx.Response(
            200,
            json={
                "content": b64encode(b"marker").decode("ascii"),
                "encoding": "base64",
            },
        ),
        httpx.Response(201, json={"content": {"sha": "new_sha"}}),
        httpx.Response(201, json={"number": 7, "html_url": "https://example/pull/7"}),
    ]

    def fake_request(method, url, *, data=None, json=None, headers=None, params=None, timeout=None):
        requests.append({"method": method, "url": url, "json": json})
        return responses.pop(0)

    monkeypatch.setattr("apps.github_app.client.httpx.request", fake_request)
    client = GitHubAppClient(api_base_url="https://api.github.test", max_retries=0)

    client.create_branch_ref("org", "repo", branch="gardener/x", sha="abc", token="t")
    sha = client.get_file_sha("org", "repo", ".gardener/plans/x.md", branch="gardener/x", token="t")
    content = client.get_file_contents(
        "org",
        "repo",
        ".gardener/plans/x.md",
        branch="gardener/x",
        token="t",
    )
    client.put_file_contents(
        "org",
        "repo",
        ".gardener/plans/x.md",
        message="m",
        content="c",
        branch="gardener/x",
        token="t",
        sha=sha,
    )
    pr = client.create_pull_request(
        "org", "repo", title="t", head="gardener/x", base="main", body="b", token="t"
    )

    assert requests[0]["json"] == {"ref": "refs/heads/gardener/x", "sha": "abc"}
    assert requests[0]["url"].endswith("/repos/org/repo/git/refs")
    assert content == "marker"
    assert requests[3]["json"]["sha"] == "existing_sha"
    assert pr["number"] == 7
