import pytest

from apps.maintenance_prs import ai_fixes
from apps.maintenance_prs.ci_repair import repair_failed_maintenance_pr_plan
from apps.maintenance_prs.models import MaintenancePRPlan
from tests.test_maintenance_pr_executor import make_plan


class FakeRepairGitHubClient:
    def __init__(self, *, file_contents=None):
        self.calls = []
        self.file_contents = dict(file_contents or {})
        self.put_contents = {}

    def create_installation_token(self, installation_id):
        self.calls.append(("create_installation_token", installation_id))
        return "ghs_token"

    def list_check_runs_for_ref(self, owner, repo, ref, *, token):
        self.calls.append(("list_check_runs_for_ref", owner, repo, ref))
        return [
            {
                "id": 123,
                "name": "pytest",
                "conclusion": "failure",
                "output": {
                    "title": "Tests failed",
                    "summary": "AssertionError: expected no dead function",
                },
            }
        ]

    def get_file_contents(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_contents", owner, repo, path, branch))
        return self.file_contents[path]

    def get_file_sha(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_sha", owner, repo, path, branch))
        return f"{path}-sha"

    def put_file_contents(self, owner, repo, path, *, message, content, branch, token, sha=None):
        self.calls.append(("put_file_contents", owner, repo, path, branch, message, sha))
        self.put_contents[path] = content
        return {"commit": {"sha": "repair_sha"}}


@pytest.mark.django_db
def test_ci_repair_updates_same_pr_branch_and_records_state(monkeypatch):
    original = "def kept():\n    return 1\n\n\ndef dead():\n    return 0\n"

    def fake_apply(path, content, plan, opportunity, progress=None):
        assert "Failed checks: pytest" in opportunity["evidence"][0]["summary"]
        return content.replace("def dead():\n    return 0\n", "")

    monkeypatch.setattr(ai_fixes, "apply_ai_fix", fake_apply)
    plan = make_plan(
        category="dead_code",
        branch_name="gardener/dead-code-ci",
        changed_paths=["core/util.py"],
        execution_status=MaintenancePRPlan.ExecutionStatus.SUCCEEDED,
        created_pr_number=7,
        created_pr_url="https://github.com/org-1/repo-1/pull/7",
    )
    client = FakeRepairGitHubClient(file_contents={"core/util.py": original})

    result = repair_failed_maintenance_pr_plan(plan_id=str(plan.id), client=client)

    plan.refresh_from_db()
    assert result["status"] == MaintenancePRPlan.CIRepairStatus.SUCCEEDED
    assert plan.ci_repair_attempts == 1
    assert plan.ci_repair_status == MaintenancePRPlan.CIRepairStatus.SUCCEEDED
    assert plan.ci_repair_error == ""
    assert "def dead()" not in client.put_contents["core/util.py"]
    assert (
        "put_file_contents",
        "org-1",
        "repo-1",
        "core/util.py",
        "gardener/dead-code-ci",
        "Repair failed checks for Refresh docs",
        "core/util.py-sha",
    ) in client.calls


@pytest.mark.django_db
def test_ci_repair_skips_when_attempt_limit_reached(settings):
    settings.GARDENER_CI_REPAIR_MAX_ATTEMPTS = 1
    plan = make_plan(
        category="dead_code",
        branch_name="gardener/dead-code-ci-limit",
        changed_paths=["core/util.py"],
        execution_status=MaintenancePRPlan.ExecutionStatus.SUCCEEDED,
        created_pr_number=7,
        created_pr_url="https://github.com/org-1/repo-1/pull/7",
        ci_repair_attempts=1,
    )

    result = repair_failed_maintenance_pr_plan(plan_id=str(plan.id))

    plan.refresh_from_db()
    assert result["status"] == MaintenancePRPlan.CIRepairStatus.SKIPPED
    assert plan.ci_repair_status == MaintenancePRPlan.CIRepairStatus.SKIPPED
    assert "attempt limit" in plan.ci_repair_error
