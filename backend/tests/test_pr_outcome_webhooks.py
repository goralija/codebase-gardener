import pytest

from apps.github_app.models import GitHubWebhookEvent
from apps.github_app.services import process_stored_github_webhook_event
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.profiles.learning import Outcome
from apps.profiles.models import GardenerProfile
from tests.test_github_webhooks import (
    create_repository,
    create_webhook_event,
    patch_session_enqueue,
    repository_payload,
)

BRANCH = "gardener/docs-refresh"
PR_NUMBER = 42


def make_plan(repository, *, category="docs", title="Refresh docs", merge_commit_sha=""):
    return MaintenancePRPlan.objects.create(
        repository=repository,
        gardening_session_id="session_webhook",
        branch_name=BRANCH,
        title=title,
        category=category,
        risk_tier="tier_1_autonomous",
        confidence=0.95,
        confidence_threshold=0.9,
        changed_paths=["docs/a.md"],
        pr_body_sections={},
        required_checks=[],
        created_pr_number=PR_NUMBER,
        merge_commit_sha=merge_commit_sha,
    )


def pull_request_payload(
    repository, *, action, number=PR_NUMBER, merged=False, branch=BRANCH, merge_commit_sha=None
):
    return {
        "action": action,
        "number": number,
        "installation": {"id": repository.github_installation.github_installation_id},
        "repository": repository_payload(repository.github_repository_id, repository.name),
        "pull_request": {
            "number": number,
            "merged": merged,
            "merge_commit_sha": merge_commit_sha,
            "head": {"ref": branch},
        },
    }


def review_payload(repository, *, state, number=PR_NUMBER, branch=BRANCH):
    return {
        "action": "submitted",
        "installation": {"id": repository.github_installation.github_installation_id},
        "repository": repository_payload(repository.github_repository_id, repository.name),
        "review": {"state": state},
        "pull_request": {"number": number, "head": {"ref": branch}},
    }


def ci_payload(repository, *, key, conclusion, identifier, head_branch=BRANCH):
    return {
        "action": "completed",
        "installation": {"id": repository.github_installation.github_installation_id},
        "repository": repository_payload(repository.github_repository_id, repository.name),
        key: {
            "id": identifier,
            "status": "completed",
            "conclusion": conclusion,
            "head_branch": head_branch,
        },
    }


def push_payload(repository, *, commits, ref="refs/heads/main", after="abc123"):
    return {
        "ref": ref,
        "before": "0000000",
        "after": after,
        "deleted": False,
        "commits": commits,
        "installation": {"id": repository.github_installation.github_installation_id},
        "repository": repository_payload(repository.github_repository_id, repository.name),
    }


def process(event_name, payload, delivery_id):
    event = create_webhook_event(
        event_name=event_name, payload=payload, delivery_id=delivery_id
    )
    process_stored_github_webhook_event(str(event.id))
    event.refresh_from_db()
    return event


@pytest.mark.django_db
def test_pull_request_closed_merged_records_merged_outcome(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    plan = make_plan(repository)

    event = process(
        "pull_request",
        pull_request_payload(
            repository, action="closed", merged=True, merge_commit_sha="deadbeefcafe1234"
        ),
        "pr-merged",
    )

    profile = GardenerProfile.objects.get(repository=repository)
    plan.refresh_from_db()
    assert event.status == GitHubWebhookEvent.Status.PROCESSED
    assert event.result["outcome"] == Outcome.MERGED
    assert event.result["maintenance_pr_plan_id"] == str(plan.id)
    assert profile.accepted_categories == ["docs"]
    assert plan.merge_commit_sha == "deadbeefcafe1234"


@pytest.mark.django_db
def test_pull_request_closed_unmerged_records_closed_outcome(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    make_plan(repository)

    event = process(
        "pull_request",
        pull_request_payload(repository, action="closed", merged=False),
        "pr-closed",
    )

    profile = GardenerProfile.objects.get(repository=repository)
    assert event.result["outcome"] == Outcome.CLOSED
    assert profile.rejected_categories == ["docs"]


@pytest.mark.django_db
def test_pull_request_edited_records_edited_outcome(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    make_plan(repository)

    event = process(
        "pull_request",
        pull_request_payload(repository, action="edited"),
        "pr-edited",
    )

    profile = GardenerProfile.objects.get(repository=repository)
    assert event.result["outcome"] == Outcome.EDITED
    assert len(profile.review_preferences) == 1


@pytest.mark.django_db
def test_pull_request_review_approved_records_accepted(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    make_plan(repository)

    event = process(
        "pull_request_review",
        review_payload(repository, state="approved"),
        "review-approved",
    )

    profile = GardenerProfile.objects.get(repository=repository)
    assert event.result["outcome"] == Outcome.ACCEPTED
    assert profile.accepted_categories == ["docs"]


@pytest.mark.django_db
def test_pull_request_review_changes_requested_records_rejected(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    make_plan(repository)

    event = process(
        "pull_request_review",
        review_payload(repository, state="changes_requested"),
        "review-changes",
    )

    profile = GardenerProfile.objects.get(repository=repository)
    assert event.result["outcome"] == Outcome.REJECTED
    assert profile.rejected_categories == ["docs"]


@pytest.mark.django_db
def test_workflow_run_failure_on_gardener_branch_records_failed(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    plan = make_plan(repository)

    event = process(
        "workflow_run",
        ci_payload(repository, key="workflow_run", conclusion="failure", identifier=901),
        "ci-failed",
    )

    profile = GardenerProfile.objects.get(repository=repository)
    assert event.status == GitHubWebhookEvent.Status.PROCESSED
    assert event.result["outcome"] == Outcome.FAILED
    assert event.result["maintenance_pr_plan_id"] == str(plan.id)
    # Failed is ranking-only: logged but no category list mutation.
    assert profile.rejected_categories == []
    assert profile.updated_from_pr_outcomes[0]["outcome"] == Outcome.FAILED


@pytest.mark.django_db
def test_push_revert_of_merged_gardener_pr_records_reverted(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    plan = make_plan(repository, title="Refresh docs", merge_commit_sha="deadbeefcafe1234")
    commits = [
        {
            "id": "rev123",
            "message": 'Revert "Refresh docs"\n\nThis reverts commit deadbeefcafe1234.',
            "added": [],
            "modified": ["docs/a.md"],
            "removed": [],
        }
    ]

    event = process("push", push_payload(repository, commits=commits), "push-revert")

    profile = GardenerProfile.objects.get(repository=repository)
    assert event.status == GitHubWebhookEvent.Status.PROCESSED
    assert event.result["reverted_maintenance_pr_plan_ids"] == [str(plan.id)]
    assert profile.reverted_categories == ["docs"]


@pytest.mark.django_db
def test_push_revert_matches_abbreviated_sha(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    plan = make_plan(repository, merge_commit_sha="deadbeefcafe1234567890abcdef1234567890ab")
    # `git revert` abbreviates the SHA in the commit body.
    commits = [
        {
            "id": "rev123",
            "message": 'Revert "Refresh docs"\n\nThis reverts commit deadbee.',
            "added": [],
            "modified": ["docs/a.md"],
            "removed": [],
        }
    ]

    event = process("push", push_payload(repository, commits=commits), "push-revert-abbrev")

    profile = GardenerProfile.objects.get(repository=repository)
    assert event.result["reverted_maintenance_pr_plan_ids"] == [str(plan.id)]
    assert profile.reverted_categories == ["docs"]


@pytest.mark.django_db
def test_merge_records_sha_once_and_is_idempotent(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    plan = make_plan(repository)
    payload = pull_request_payload(
        repository, action="closed", merged=True, merge_commit_sha="abc123def456"
    )

    first = process("pull_request", payload, "pr-merged-1")
    second = process("pull_request", payload, "pr-merged-2")

    plan.refresh_from_db()
    profile = GardenerProfile.objects.get(repository=repository)
    assert first.result["outcome_recorded"] is True
    assert second.result["outcome_recorded"] is False
    assert plan.merge_commit_sha == "abc123def456"
    assert profile.accepted_categories == ["docs"]
    assert len(profile.updated_from_pr_outcomes) == 1


@pytest.mark.django_db
def test_push_revert_without_recorded_merge_sha_is_not_reverted(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    # Plan was created but never merged -> no merge_commit_sha -> cannot revert.
    make_plan(repository, title="Refresh docs", merge_commit_sha="")
    commits = [
        {
            "id": "rev123",
            "message": 'Revert "Refresh docs"\n\nThis reverts commit deadbeefcafe1234.',
            "added": [],
            "modified": ["docs/a.md"],
            "removed": [],
        }
    ]

    event = process("push", push_payload(repository, commits=commits), "push-revert-unmerged")

    assert event.status == GitHubWebhookEvent.Status.PROCESSED
    assert "reverted_maintenance_pr_plan_ids" not in event.result
    assert not GardenerProfile.objects.filter(repository=repository).exists()


@pytest.mark.django_db
def test_non_gardener_pull_request_is_ignored(monkeypatch):
    patch_session_enqueue(monkeypatch)
    repository = create_repository()
    # No plan created -> PR is not gardener-authored.

    event = process(
        "pull_request",
        pull_request_payload(
            repository, action="closed", merged=True, number=777, branch="feature/x"
        ),
        "pr-foreign",
    )

    assert event.status == GitHubWebhookEvent.Status.IGNORED
    assert event.result["reason"] == "pull_request_not_gardener_authored"
    assert not GardenerProfile.objects.filter(repository=repository).exists()


@pytest.mark.django_db
def test_open_action_still_triggers_session_not_outcome(monkeypatch):
    queued = patch_session_enqueue(monkeypatch)
    repository = create_repository()
    make_plan(repository)

    event = process(
        "pull_request",
        pull_request_payload(repository, action="opened"),
        "pr-opened-trigger",
    )

    assert event.status == GitHubWebhookEvent.Status.PROCESSED
    assert "outcome" not in event.result
    assert len(queued) == 1
    assert not GardenerProfile.objects.filter(repository=repository).exists()
