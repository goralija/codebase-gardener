import pytest

from apps.analysis.constitution_pr import (
    GARDENER_PATH,
    PROPOSAL_MARKER,
    maybe_open_constitution_pr,
    render_gardener_md,
)
from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError
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
        create_pr_error=None,
        existing_pr=None,
        existing_branch_content=None,
        file_sha=None,
    ):
        self.calls = []
        self.create_branch_error = create_branch_error
        self.create_pr_error = create_pr_error
        self.existing_pr = existing_pr
        self.existing_branch_content = existing_branch_content
        self.file_sha = file_sha
        self.written_content = ""

    def create_installation_token(self, installation_id):
        self.calls.append(("create_installation_token", installation_id))
        return "ghs_token"

    def get_branch_ref(self, owner, repo, branch, *, token):
        self.calls.append(("get_branch_ref", owner, repo, branch))
        return "base_sha"

    def create_branch_ref(self, owner, repo, *, branch, sha, token):
        self.calls.append(("create_branch_ref", owner, repo, branch, sha))
        if self.create_branch_error:
            raise self.create_branch_error
        return {"ref": f"refs/heads/{branch}"}

    def get_file_contents(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_contents", owner, repo, path, branch))
        if self.existing_branch_content is None:
            raise GitHubAPIError("not found", status_code=404)
        return self.existing_branch_content

    def get_file_sha(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_sha", owner, repo, path, branch))
        return self.file_sha

    def put_file_contents(self, owner, repo, path, *, message, content, branch, token, sha=None):
        self.calls.append(("put_file_contents", owner, repo, path, branch, sha))
        self.written_content = content
        return {"content": {"path": path}}

    def create_pull_request(self, owner, repo, *, title, head, base, body, token, draft=False):
        self.calls.append(("create_pull_request", owner, repo, head, base, draft))
        if self.create_pr_error:
            raise self.create_pr_error
        return {"number": 7, "html_url": "https://github.com/org/repo/pull/7"}

    def find_pull_request(self, owner, repo, *, head, base, token):
        self.calls.append(("find_pull_request", owner, repo, head, base))
        return self.existing_pr


@pytest.mark.django_db
def test_maybe_open_constitution_pr_creates_draft_pr_for_missing_gardener():
    repository = make_repository()
    client = FakeGitHubClient()

    result = maybe_open_constitution_pr(
        repository=repository,
        artifacts=_artifacts(repository),
        client=client,
    )

    assert result["created"] is True
    assert result["pr_number"] == 7
    assert PROPOSAL_MARKER in client.written_content
    assert "## Protected Modules" in client.written_content
    assert "`core/permissions/**`" in client.written_content
    assert ("create_pull_request", "org-1", "repo-1", result["branch"], "main", True) in client.calls
    audit = AuditEvent.objects.get(event_type=AuditEvent.EventType.MAINTENANCE_PR_CREATED)
    assert audit.repository_id == repository.id
    assert audit.metadata["path"] == GARDENER_PATH


@pytest.mark.django_db
def test_maybe_open_constitution_pr_skips_when_constitution_not_missing():
    repository = make_repository()
    artifacts = _artifacts(repository)
    artifacts["constitution"]["open_questions"] = []
    client = FakeGitHubClient()

    result = maybe_open_constitution_pr(
        repository=repository,
        artifacts=artifacts,
        client=client,
    )

    assert result == {"created": False, "reason": "constitution_not_missing"}
    assert client.calls == []


@pytest.mark.django_db
def test_maybe_open_constitution_pr_reuses_existing_marked_branch_and_pr():
    repository = make_repository()
    client = FakeGitHubClient(
        create_branch_error=GitHubAPIError("exists", status_code=422),
        create_pr_error=GitHubAPIError("pull exists", status_code=422),
        existing_branch_content=PROPOSAL_MARKER,
        existing_pr={"number": 8, "html_url": "https://github.com/org/repo/pull/8"},
        file_sha="old_sha",
    )

    result = maybe_open_constitution_pr(
        repository=repository,
        artifacts=_artifacts(repository),
        client=client,
    )

    assert result["pr_number"] == 8
    assert any(call[0] == "find_pull_request" for call in client.calls)
    assert any(call[0] == "put_file_contents" and call[-1] == "old_sha" for call in client.calls)


@pytest.mark.django_db
def test_render_gardener_md_includes_review_warning_and_conservative_defaults():
    repository = make_repository()

    content = render_gardener_md(repository=repository, artifacts=_artifacts(repository))

    assert PROPOSAL_MARKER in content
    assert "Review and edit this draft before merging" in content
    assert "documentation updates" in content
    assert "Do not auto-merge Gardener PRs" in content


def make_repository():
    organization = create_organization(1)
    installation = create_installation(organization, 1)
    return create_repository(organization, installation, 1)


def _artifacts(repository):
    return {
        "constitution": {
            "open_questions": [
                {
                    "severity": "blocking",
                    "question": "No repository constitution (GARDENER.md) found; cannot derive rules.",
                }
            ],
        },
        "snapshot": {
            "signals": {
                "hotspots": [
                    {
                        "path": "core/permissions/checks.py",
                        "summary": "Permission hotspot.",
                    },
                    {
                        "path": "tenants/models.py",
                        "summary": "Tenancy hotspot.",
                    },
                ],
                "dependency_cycles": [],
                "ownership_risks": [],
                "test_gaps": [],
            }
        },
        "entropy": {
            "score": {
                "classification": "no_autonomy",
                "overall": 58.7,
            }
        },
    }
