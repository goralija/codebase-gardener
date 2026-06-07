import httpx
import pytest
from base64 import b64encode
from django.utils import timezone

from apps.billing.models import Subscription
from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError
from apps.maintenance_prs.executor import (
    PlanNotExecutableError,
    execute_maintenance_pr_plan,
)
from apps.maintenance_prs.docs_fixes import apply_docs_maintenance_note
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.triggers.models import RepositoryAutomationPolicy
from apps.triggers.policy import CONSERVATIVE_AUTONOMY_PR_BLOCK_REASON
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
        file_contents=None,
        file_shas=None,
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
        self.file_contents = dict(file_contents or {})
        self.file_shas = dict(file_shas or {})
        self.put_contents = {}
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
        if path in self.file_shas:
            return self.file_shas[path]
        return self.marker_sha

    def get_file_contents(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_contents", owner, repo, path, branch))
        if self.get_file_contents_error is not None:
            raise self.get_file_contents_error
        self._maybe_fail("get_file_contents")
        if path in self.file_contents:
            return self.file_contents[path]
        return self.marker_content or ""

    def put_file_contents(self, owner, repo, path, *, message, content, branch, token, sha=None):
        self.calls.append(("put_file_contents", owner, repo, path, branch, sha))
        self._maybe_fail("put_file_contents")
        self.put_contents[path] = content
        return {"commit": {"sha": "commit_sha"}}

    def create_pull_request(self, owner, repo, *, title, head, base, body, token, draft=False):
        self.calls.append(("create_pull_request", owner, repo, head, base, draft))
        if self.create_pr_error is not None:
            raise self.create_pr_error
        self._maybe_fail("create_pull_request")
        if self.pr_response is not None:
            return self.pr_response
        return {"number": 42, "html_url": "https://github.com/org-1/repo-1/pull/42"}

    def add_labels(self, owner, repo, issue_number, labels, *, token):
        self.calls.append(("add_labels", owner, repo, issue_number, tuple(labels)))
        self.applied_labels = list(labels)
        return [{"name": label} for label in labels]

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
    Subscription.objects.create(
        organization=organization,
        autonomous_pr_add_on_enabled=True,
    )
    installation = create_installation(organization, identifier)
    repository = create_repository(organization, installation, identifier)
    RepositoryAutomationPolicy.objects.create(
        organization=organization,
        repository=repository,
        autonomy_mode=RepositoryAutomationPolicy.AutonomyMode.AUTONOMOUS,
    )
    return repository


def make_plan(repository=None, **overrides):
    repository = repository or make_repository()
    defaults = dict(
        repository=repository,
        gardening_session_id="session_exec",
        branch_name="gardener/docs-refresh",
        title="Refresh docs",
        category="docs",
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
def test_execute_ai_dead_code_fix_authors_pr_and_applies_risk_labels(monkeypatch):
    from apps.maintenance_prs import ai_fixes

    kept = "".join(f"def used_{i}():\n    return {i}\n\n\n" for i in range(8))
    original = kept + "def dead():\n    return 0\n"
    monkeypatch.setattr(
        ai_fixes, "complete", lambda *a, **k: f"```python\n{kept.rstrip()}\n```"
    )

    plan = make_plan(
        category="dead_code",
        branch_name="gardener/dead-code",
        title="Remove dead code",
        changed_paths=["core/util.py"],
    )
    client = FakeGitHubClient(
        file_contents={"core/util.py": original},
        file_shas={"core/util.py": "util_sha"},
    )

    result = execute_maintenance_pr_plan(plan, client=client)

    assert result["created_pr_number"] == 42
    # AI edit was committed to the source file (dead symbol removed).
    assert "def dead()" not in client.put_contents["core/util.py"]
    # PR labeled by risk tier / confidence / category.
    assert ("add_labels", "org-1", "repo-1", 42,
            ("gardener:tier-1-autonomous", "gardener:risk-low", "gardener:confidence-high",
             "gardener:category-dead-code")) in client.calls


@pytest.mark.django_db
def test_execute_ai_fix_authors_multiple_files(monkeypatch):
    from apps.maintenance_prs import ai_fixes

    def fake_apply(path, content, plan, opportunity, progress=None):
        return content.replace("def dead():\n    return 0\n", "")

    monkeypatch.setenv("GARDENER_AI_FIX_WORKERS", "2")
    monkeypatch.setattr(ai_fixes, "apply_ai_fix", fake_apply)

    plan = make_plan(
        category="dead_code",
        branch_name="gardener/dead-code-multi",
        title="Remove dead code",
        changed_paths=["core/a.py", "core/b.py"],
    )
    client = FakeGitHubClient(
        file_contents={
            "core/a.py": "def kept_a():\n    return 1\n\n\ndef dead():\n    return 0\n",
            "core/b.py": "def kept_b():\n    return 2\n\n\ndef dead():\n    return 0\n",
        },
        file_shas={"core/a.py": "a_sha", "core/b.py": "b_sha"},
    )

    execute_maintenance_pr_plan(plan, client=client)

    put_paths = [call[3] for call in client.calls if call[0] == "put_file_contents"]
    assert put_paths == [
        ".gardener/plans/gardener-dead-code-multi.md",
        "core/a.py",
        "core/b.py",
    ]
    assert "def dead()" not in client.put_contents["core/a.py"]
    assert "def dead()" not in client.put_contents["core/b.py"]


@pytest.mark.django_db
def test_execute_ai_fix_failure_fails_plan_without_pr(monkeypatch):
    from apps.maintenance_prs import ai_fixes
    from apps.maintenance_prs.ai_fixes import AIFixError
    from apps.maintenance_prs.executor import PlanNotExecutableError

    def _boom(*a, **k):
        raise AIFixError("invalid python")

    monkeypatch.setattr(ai_fixes, "apply_ai_fix", _boom)

    plan = make_plan(
        category="dead_code",
        branch_name="gardener/dead-code-2",
        changed_paths=["core/util.py"],
    )
    client = FakeGitHubClient(file_contents={"core/util.py": "x = 1\n"})

    # The only file fails to author -> 0 changes -> plan fails, no PR opened.
    with pytest.raises(PlanNotExecutableError, match="no file changes"):
        execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.FAILED
    assert "create_pull_request" not in _names(client)


@pytest.mark.django_db
def test_execute_ships_files_that_authored_and_skips_failures(monkeypatch):
    from apps.maintenance_prs import ai_fixes
    from apps.maintenance_prs.ai_fixes import AIFixError

    def _author(path, content, *a, **k):
        if path == "core/bad.py":
            raise AIFixError("no SEARCH block matched")
        return content + "# fixed\n"

    monkeypatch.setattr(ai_fixes, "apply_ai_fix", _author)

    plan = make_plan(
        category="dead_code",
        branch_name="gardener/dead-code-partial",
        changed_paths=["core/good.py", "core/bad.py"],
    )
    client = FakeGitHubClient(
        file_contents={"core/good.py": "x = 1\n", "core/bad.py": "y = 2\n"},
        file_shas={"core/good.py": "good_sha", "core/bad.py": "bad_sha"},
    )

    result = execute_maintenance_pr_plan(plan, client=client)

    # The good file ships; the failing file is skipped, not fatal. PR still opens.
    assert "core/good.py" in client.put_contents
    assert "core/bad.py" not in client.put_contents
    assert "create_pull_request" in _names(client)
    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    assert result["created_pr_number"] == 42


@pytest.mark.django_db
def test_execute_happy_path_creates_branch_and_pr():
    plan = make_plan()
    client = FakeGitHubClient(
        file_contents={"docs/api.md": "# API\n"},
        file_shas={"docs/api.md": "api_sha"},
    )

    result = execute_maintenance_pr_plan(plan, client=client)

    assert _names(client) == [
        "create_installation_token",
        "get_branch_ref",
        "create_branch_ref",
        "get_file_sha",
        "put_file_contents",
        "get_file_contents",
        "get_file_sha",
        "put_file_contents",
        "create_pull_request",
        "add_labels",
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
    assert "## Gardener maintenance note" in client.put_contents["docs/api.md"]


@pytest.mark.django_db
def test_execute_assisted_plan_creates_draft_pr(monkeypatch):
    from apps.maintenance_prs import ai_fixes

    monkeypatch.setattr(
        ai_fixes,
        "apply_ai_fix",
        lambda _path, content, _plan, _opportunity, progress=None: (
            f"{content.rstrip()}\n\n"
            "def test_added_by_gardener():\n"
            "    assert True\n"
        ),
    )
    plan = make_plan(
        category="tests",
        risk_tier="tier_2_assisted",
        changed_paths=["tests/test_gap.py"],
        required_checks=["test_review"],
    )
    client = FakeGitHubClient(
        file_contents={"tests/test_gap.py": "def test_existing():\n    assert True\n"},
        file_shas={"tests/test_gap.py": "test_sha"},
    )

    execute_maintenance_pr_plan(plan, client=client)

    create_pr_calls = [call for call in client.calls if call[0] == "create_pull_request"]
    assert create_pr_calls == [
        ("create_pull_request", "org-1", "repo-1", "gardener/docs-refresh", "main", True)
    ]
    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    assert plan.created_pr_url == "https://github.com/org-1/repo-1/pull/42"


@pytest.mark.django_db
def test_execute_docs_plan_updates_markdown_paths_and_writes_marker():
    plan = make_plan(
        category="docs",
        changed_paths=["README.md", "docs/guide.md", "src/app.py", "docs/*.md"],
    )
    client = FakeGitHubClient(
        file_contents={
            "README.md": "# Project\n",
            "docs/guide.md": "# Guide\n",
        },
        file_shas={
            "README.md": "readme_sha",
            "docs/guide.md": "guide_sha",
        },
    )

    execute_maintenance_pr_plan(plan, client=client)

    marker_path = ".gardener/plans/gardener-docs-refresh.md"
    assert set(client.put_contents) == {"README.md", "docs/guide.md", marker_path}
    assert "## Gardener maintenance note" in client.put_contents["README.md"]
    assert f"plan `{plan.id}`" in client.put_contents["docs/guide.md"]
    assert "src/app.py" not in client.put_contents
    assert "docs/*.md" not in client.put_contents

    readme_put = next(c for c in client.calls if c[0] == "put_file_contents" and c[3] == "README.md")
    guide_put = next(c for c in client.calls if c[0] == "put_file_contents" and c[3] == "docs/guide.md")
    assert readme_put[5] == "readme_sha"
    assert guide_put[5] == "guide_sha"
    marker_put_index = next(
        index
        for index, call in enumerate(client.calls)
        if call[0] == "put_file_contents" and call[3] == marker_path
    )
    readme_put_index = next(
        index
        for index, call in enumerate(client.calls)
        if call[0] == "put_file_contents" and call[3] == "README.md"
    )
    assert marker_put_index < readme_put_index


@pytest.mark.django_db
def test_docs_maintenance_note_replaces_existing_section_idempotently():
    plan = make_plan(category="docs")
    first = apply_docs_maintenance_note("# Project\n", plan)
    second = apply_docs_maintenance_note(first, plan)

    assert second == first
    assert first.count("## Gardener maintenance note") == 1
    assert first.count(f"gardener-maintenance-note:start {plan.id}") == 1


@pytest.mark.django_db
def test_unsupported_tier_one_category_is_not_executable():
    plan = make_plan(
        category="lint_format",
        changed_paths=["src/app.py", "README.md"],
    )
    client = FakeGitHubClient(file_contents={"README.md": "# Project\n"})

    with pytest.raises(PlanNotExecutableError, match="No implemented file fix"):
        execute_maintenance_pr_plan(plan, client=client)

    assert client.calls == []


@pytest.mark.django_db
def test_docs_plan_without_existing_markdown_target_does_not_open_marker_only_pr():
    plan = make_plan(changed_paths=["docs/missing.md"])
    client = FakeGitHubClient(
        get_file_contents_error=GitHubAPIError("not found", status_code=404),
    )

    with pytest.raises(PlanNotExecutableError, match="no Markdown file changes"):
        execute_maintenance_pr_plan(plan, client=client)

    marker_path = ".gardener/plans/gardener-docs-refresh.md"
    assert set(client.put_contents) == {marker_path}
    assert "create_pull_request" not in _names(client)
    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.FAILED


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
def test_existing_branch_missing_marker_uses_suffixed_branch():
    plan = make_plan()

    class BranchCollisionClient(FakeGitHubClient):
        def create_branch_ref(self, owner, repo, *, branch, sha, token):
            self.calls.append(("create_branch_ref", owner, repo, branch, sha))
            if branch == "gardener/docs-refresh":
                raise GitHubAPIError("exists", status_code=422)
            return {"ref": f"refs/heads/{branch}"}

        def get_file_contents(self, owner, repo, path, *, branch, token):
            if path == ".gardener/plans/gardener-docs-refresh.md":
                self.calls.append(("get_file_contents", owner, repo, path, branch))
                raise GitHubAPIError("not found", status_code=404)
            return super().get_file_contents(owner, repo, path, branch=branch, token=token)

    client = BranchCollisionClient(file_contents={"docs/api.md": "# API\n"})

    execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.branch_name == "gardener/docs-refresh-2"
    assert plan.created_branch_ref == "refs/heads/gardener/docs-refresh-2"
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    assert (
        "create_branch_ref",
        "org-1",
        "repo-1",
        "gardener/docs-refresh",
        "base_sha",
    ) in client.calls
    assert (
        "create_branch_ref",
        "org-1",
        "repo-1",
        "gardener/docs-refresh-2",
        "base_sha",
    ) in client.calls
    assert any(
        call[:4]
        == (
            "put_file_contents",
            "org-1",
            "repo-1",
            ".gardener/plans/gardener-docs-refresh-2.md",
        )
        for call in client.calls
    )
    assert ("create_pull_request", "org-1", "repo-1", "gardener/docs-refresh-2", "main", False) in client.calls


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
def test_disabled_autonomous_pr_add_on_does_not_block_existing_plan_execution():
    plan = make_plan()
    Subscription.objects.filter(
        organization=plan.repository.organization,
    ).update(
        autonomous_pr_add_on_enabled=False,
    )
    client = FakeGitHubClient()

    result = execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    assert result["created_pr_number"] == 42


@pytest.mark.django_db
def test_conservative_autonomy_mode_blocks_existing_plan_execution():
    plan = make_plan()
    policy = RepositoryAutomationPolicy.get_or_create_for_repository(plan.repository)
    policy.autonomy_mode = RepositoryAutomationPolicy.AutonomyMode.CONSERVATIVE
    policy.save(update_fields=["autonomy_mode", "updated_at"])
    client = FakeGitHubClient()

    with pytest.raises(PlanNotExecutableError) as exc_info:
        execute_maintenance_pr_plan(plan, client=client)

    assert str(exc_info.value) == CONSERVATIVE_AUTONOMY_PR_BLOCK_REASON
    assert client.calls == []
    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.PENDING


@pytest.mark.django_db
def test_claim_ignores_disabled_autonomous_pr_add_on_in_db():
    plan = make_plan()
    Subscription.objects.filter(
        organization=plan.repository.organization,
    ).update(
        autonomous_pr_add_on_enabled=False,
    )
    client = FakeGitHubClient()

    execute_maintenance_pr_plan(plan, client=client)

    plan.refresh_from_db()
    assert plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED


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
    assisted = make_plan(
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
    assert executable == [approved, failed, assisted]


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
