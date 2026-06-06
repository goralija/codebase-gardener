import pytest
import yaml

from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError
from apps.profiles.models import GardenerProfile
from apps.profiles.sync import (
    PROFILE_FILE_PATH,
    PROFILE_SYNC_BRANCH,
    render_profile_yaml,
    sync_profile_to_repo,
)
from tests.test_product_models import (
    create_installation,
    create_organization,
    create_repository,
)


class FakeGitHubClient:
    def __init__(
        self,
        *,
        current_contents=None,
        get_contents_error=None,
        create_branch_error=None,
        create_pr_error=None,
        existing_pr=None,
        file_sha=None,
        pr_response=None,
    ):
        self.calls = []
        self.current_contents = current_contents
        self.get_contents_error = get_contents_error
        self.create_branch_error = create_branch_error
        self.create_pr_error = create_pr_error
        self.existing_pr = existing_pr
        self.file_sha = file_sha
        self.pr_response = pr_response

    def create_installation_token(self, installation_id):
        self.calls.append(("create_installation_token", installation_id))
        return "ghs_token"

    def get_file_contents(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_contents", owner, repo, path, branch))
        if self.get_contents_error is not None:
            raise self.get_contents_error
        if self.current_contents is None:
            raise GitHubAPIError("not found", status_code=404)
        return self.current_contents

    def get_branch_ref(self, owner, repo, branch, *, token):
        self.calls.append(("get_branch_ref", owner, repo, branch))
        return "base_sha"

    def create_branch_ref(self, owner, repo, *, branch, sha, token):
        self.calls.append(("create_branch_ref", owner, repo, branch, sha))
        if self.create_branch_error is not None:
            raise self.create_branch_error
        return {"ref": f"refs/heads/{branch}"}

    def get_file_sha(self, owner, repo, path, *, branch, token):
        self.calls.append(("get_file_sha", owner, repo, path, branch))
        return self.file_sha

    def put_file_contents(self, owner, repo, path, *, message, content, branch, token, sha=None):
        self.calls.append(("put_file_contents", owner, repo, path, branch, sha))
        self.put_content = content
        return {"commit": {"sha": "commit_sha"}}

    def create_pull_request(self, owner, repo, *, title, head, base, body, token):
        self.calls.append(("create_pull_request", owner, repo, head, base))
        if self.create_pr_error is not None:
            raise self.create_pr_error
        if self.pr_response is not None:
            return self.pr_response
        return {"number": 7, "html_url": "https://github.com/org-1/repo-1/pull/7"}

    def find_pull_request(self, owner, repo, *, head, base, token):
        self.calls.append(("find_pull_request", owner, repo, head, base))
        return self.existing_pr


def _names(client):
    return [call[0] for call in client.calls]


def make_repository(identifier=1):
    organization = create_organization(identifier)
    installation = create_installation(organization, identifier)
    return create_repository(organization, installation, identifier)


def make_profile(repository=None, **overrides):
    repository = repository or make_repository()
    defaults = dict(
        repository=repository,
        preferred_pr_size="small",
        accepted_categories=["dependency_patch"],
        rejected_categories=["formatting"],
        reverted_categories=[],
        learned_protected_patterns=[{"pattern": "infra/", "reason": "Reverted."}],
        review_preferences=["Review auth edits."],
        updated_from_pr_outcomes=[
            {"maintenance_pr_id": "p1", "outcome": "merged", "category": "dependency_patch"},
            {"maintenance_pr_id": "p2", "outcome": "accepted", "category": "dependency_patch"},
            {"maintenance_pr_id": "p3", "outcome": "rejected", "category": "formatting"},
        ],
    )
    defaults.update(overrides)
    return GardenerProfile.objects.create(**defaults)


# ---------------------------------------------------------------------------
# render_profile_yaml
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_render_profile_yaml_matches_doc16_shape():
    profile = make_profile()

    document = yaml.safe_load(render_profile_yaml(profile))

    assert document["version"] == 1
    repository = document["repository"]
    assert repository["preferred_pr_size"] == "small"
    assert repository["preferred_pr_categories"] == {
        "accepted": ["dependency_patch"],
        "rejected": ["formatting"],
    }
    assert repository["protected_patterns_learned"] == [
        {"pattern": "infra/", "reason": "Reverted."}
    ]
    assert repository["review_preferences"] == ["Review auth edits."]


@pytest.mark.django_db
def test_render_profile_yaml_counts_outcome_categories():
    profile = make_profile()

    outcomes = yaml.safe_load(render_profile_yaml(profile))["outcomes"]

    # merged + accepted both bucket into accepted_categories.
    assert outcomes["accepted_categories"] == {"dependency_patch": 2}
    assert outcomes["rejected_categories"] == {"formatting": 1}
    assert outcomes["reverted_categories"] == {}


@pytest.mark.django_db
def test_render_profile_yaml_caps_notes():
    from apps.profiles.sync import PROFILE_NOTES_LIMIT

    outcomes = [
        {"maintenance_pr_id": f"p{i}", "outcome": "merged", "category": "docs"}
        for i in range(PROFILE_NOTES_LIMIT + 10)
    ]
    profile = make_profile(updated_from_pr_outcomes=outcomes)

    document = yaml.safe_load(render_profile_yaml(profile))

    assert len(document["notes"]) == PROFILE_NOTES_LIMIT
    # Counts still reflect the full history, not just the capped notes.
    assert document["outcomes"]["accepted_categories"]["docs"] == PROFILE_NOTES_LIMIT + 10


@pytest.mark.django_db
def test_render_profile_yaml_is_deterministic():
    profile = make_profile()
    assert render_profile_yaml(profile) == render_profile_yaml(profile)


# ---------------------------------------------------------------------------
# sync_profile_to_repo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sync_no_op_when_file_matches():
    profile = make_profile()
    rendered = render_profile_yaml(profile)
    client = FakeGitHubClient(current_contents=rendered)

    result = sync_profile_to_repo(profile, client=client)

    assert result["proposed"] is False
    assert result["reason"] == "up_to_date"
    assert _names(client) == ["create_installation_token", "get_file_contents"]
    assert not AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.GARDENER_PROFILE_PR_PROPOSED
    ).exists()


@pytest.mark.django_db
def test_sync_creates_branch_put_and_pr_when_file_absent():
    profile = make_profile()
    client = FakeGitHubClient(current_contents=None)

    result = sync_profile_to_repo(profile, client=client)

    assert result["proposed"] is True
    assert result["pr_number"] == 7
    assert _names(client) == [
        "create_installation_token",
        "get_file_contents",
        "get_branch_ref",
        "create_branch_ref",
        "get_file_sha",
        "put_file_contents",
        "create_pull_request",
    ]
    assert client.put_content == render_profile_yaml(profile)
    put_call = next(c for c in client.calls if c[0] == "put_file_contents")
    assert put_call[3] == PROFILE_FILE_PATH
    assert put_call[4] == PROFILE_SYNC_BRANCH

    audit = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.GARDENER_PROFILE_PR_PROPOSED
    )
    assert audit.metadata["pr_number"] == 7
    assert audit.metadata["branch"] == PROFILE_SYNC_BRANCH


@pytest.mark.django_db
def test_sync_updates_existing_file_with_sha():
    profile = make_profile()
    client = FakeGitHubClient(current_contents="version: 0\n", file_sha="existing_sha")

    sync_profile_to_repo(profile, client=client)

    put_call = next(c for c in client.calls if c[0] == "put_file_contents")
    assert put_call[5] == "existing_sha"


@pytest.mark.django_db
def test_sync_tolerates_existing_branch():
    profile = make_profile()
    client = FakeGitHubClient(
        current_contents=None,
        create_branch_error=GitHubAPIError("exists", status_code=422),
    )

    result = sync_profile_to_repo(profile, client=client)

    assert result["proposed"] is True
    assert "put_file_contents" in _names(client)


@pytest.mark.django_db
def test_sync_reuses_existing_open_pr():
    profile = make_profile()
    client = FakeGitHubClient(
        current_contents=None,
        create_pr_error=GitHubAPIError("exists", status_code=422),
        existing_pr={"number": 99, "html_url": "https://github.com/org-1/repo-1/pull/99"},
    )

    result = sync_profile_to_repo(profile, client=client)

    assert result["proposed"] is True
    assert result["pr_number"] == 99
    assert "find_pull_request" in _names(client)


@pytest.mark.django_db
def test_sync_propagates_non_404_get_contents_error():
    profile = make_profile()
    client = FakeGitHubClient(
        get_contents_error=GitHubAPIError("boom", status_code=500)
    )

    with pytest.raises(GitHubAPIError):
        sync_profile_to_repo(profile, client=client)


@pytest.mark.django_db
def test_sync_audits_failure():
    profile = make_profile()
    client = FakeGitHubClient(
        current_contents=None,
        create_pr_error=GitHubAPIError("boom", status_code=500),
    )

    with pytest.raises(GitHubAPIError):
        sync_profile_to_repo(profile, client=client)

    audit = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.GARDENER_PROFILE_PR_FAILED
    )
    assert "boom" in audit.metadata["error"]
    assert not AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.GARDENER_PROFILE_PR_PROPOSED
    ).exists()


@pytest.mark.django_db
def test_sync_skips_inactive_repository():
    organization = create_organization(50)
    installation = create_installation(organization, 50)
    repository = create_repository(
        organization, installation, 50, unselected_at="2026-06-06T00:00:00Z"
    )
    profile = make_profile(repository=repository)
    client = FakeGitHubClient()

    result = sync_profile_to_repo(profile, client=client)

    assert result["proposed"] is False
    assert result["reason"] == "repository_inactive"
    # No GitHub calls at all — not even a token request.
    assert client.calls == []


@pytest.mark.django_db
def test_sync_no_op_when_file_semantically_equal_despite_formatting():
    profile = make_profile()
    # Re-dump with sorted keys to perturb formatting; content is equivalent.
    reformatted = yaml.safe_dump(
        yaml.safe_load(render_profile_yaml(profile)), sort_keys=True
    )
    client = FakeGitHubClient(current_contents=reformatted)

    result = sync_profile_to_repo(profile, client=client)

    assert result["proposed"] is False
    assert result["reason"] == "up_to_date"
    assert "put_file_contents" not in _names(client)
