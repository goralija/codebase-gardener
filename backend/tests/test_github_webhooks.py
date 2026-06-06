import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import CustomerOrganization
from apps.common.models import AuditEvent
from apps.github_app.models import GitHubInstallation, GitHubWebhookEvent
from apps.github_app.services import (
    ingest_github_webhook_delivery,
    process_stored_github_webhook_event,
)
from apps.repositories.models import ManagedRepository
from apps.sessions.models import GardeningSession


WEBHOOK_URL = "/api/v1/github-app/webhooks/"
WEBHOOK_SECRET = "It's a Secret to Everybody"


@pytest.mark.django_db
def test_webhook_endpoint_accepts_signed_delivery_persists_payload_and_queues_task(
    settings,
    monkeypatch,
):
    settings.GITHUB_WEBHOOK_SECRET = WEBHOOK_SECRET
    queued_event_ids = []
    monkeypatch.setattr(
        "apps.github_app.views.process_github_webhook_event.delay",
        lambda event_id: queued_event_ids.append(event_id),
    )
    payload = {"zen": "Keep it logically awesome.", "hook_id": 123}

    response = post_webhook(payload=payload, event_name="ping", delivery_id="delivery-1")

    event = GitHubWebhookEvent.objects.get()
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "delivery_id": "delivery-1"}
    assert event.delivery_id == "delivery-1"
    assert event.event == "ping"
    assert event.payload == payload
    assert event.status == GitHubWebhookEvent.Status.QUEUED
    assert queued_event_ids == [str(event.id)]
    assert WEBHOOK_SECRET not in repr(event.payload)


@pytest.mark.django_db
def test_webhook_endpoint_dedupes_delivery_without_requeue(settings, monkeypatch):
    settings.GITHUB_WEBHOOK_SECRET = WEBHOOK_SECRET
    queued_event_ids = []
    monkeypatch.setattr(
        "apps.github_app.views.process_github_webhook_event.delay",
        lambda event_id: queued_event_ids.append(event_id),
    )
    payload = {"zen": "Design for redelivery."}

    first_response = post_webhook(payload=payload, event_name="ping", delivery_id="same")
    second_response = post_webhook(payload=payload, event_name="ping", delivery_id="same")

    assert first_response.status_code == 202
    assert first_response.json()["status"] == "accepted"
    assert second_response.status_code == 202
    assert second_response.json() == {"status": "duplicate", "delivery_id": "same"}
    assert GitHubWebhookEvent.objects.count() == 1
    assert len(queued_event_ids) == 1


@pytest.mark.django_db
def test_webhook_endpoint_requeues_received_duplicate_after_queue_failure(
    settings,
    monkeypatch,
):
    settings.GITHUB_WEBHOOK_SECRET = WEBHOOK_SECRET
    queued_event_ids = []

    def flaky_delay(event_id: str):
        queued_event_ids.append(event_id)
        if len(queued_event_ids) == 1:
            raise RuntimeError("broker unavailable")
        return SimpleNamespace(id="task-2")

    monkeypatch.setattr(
        "apps.github_app.views.process_github_webhook_event.delay",
        flaky_delay,
    )
    payload = {"zen": "retry the handoff"}

    first_response = post_webhook(
        payload=payload,
        event_name="ping",
        delivery_id="queue-failure",
    )
    event = GitHubWebhookEvent.objects.get(delivery_id="queue-failure")
    second_response = post_webhook(
        payload=payload,
        event_name="ping",
        delivery_id="queue-failure",
    )

    event.refresh_from_db()
    assert first_response.status_code == 503
    assert first_response.json()["code"] == "github_webhook_queue_unavailable"
    assert second_response.status_code == 202
    assert second_response.json() == {
        "status": "requeued",
        "delivery_id": "queue-failure",
    }
    assert event.status == GitHubWebhookEvent.Status.QUEUED
    assert event.last_error == ""
    assert queued_event_ids == [str(event.id), str(event.id)]


@pytest.mark.django_db
@pytest.mark.parametrize("signature", ["sha256=bad", None])
def test_webhook_endpoint_rejects_invalid_or_missing_signature(settings, signature):
    settings.GITHUB_WEBHOOK_SECRET = WEBHOOK_SECRET

    response = post_webhook(
        payload={"zen": "nope"},
        event_name="ping",
        delivery_id="bad-signature",
        signature=signature,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "invalid_github_webhook_signature"
    assert not GitHubWebhookEvent.objects.exists()


@pytest.mark.django_db
def test_webhook_endpoint_requires_configured_secret(settings):
    settings.GITHUB_WEBHOOK_SECRET = ""

    response = post_webhook(payload={"zen": "no secret"}, event_name="ping")

    assert response.status_code == 500
    assert response.json()["code"] == "server_configuration_error"
    assert not GitHubWebhookEvent.objects.exists()


@pytest.mark.django_db
def test_webhook_endpoint_rejects_malformed_json_after_valid_signature(settings):
    settings.GITHUB_WEBHOOK_SECRET = WEBHOOK_SECRET
    body = b"{bad-json"

    response = APIClient().post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_GITHUB_DELIVERY="malformed",
        HTTP_X_GITHUB_EVENT="ping",
        HTTP_X_HUB_SIGNATURE_256=signature_for(body),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_github_webhook_payload"
    assert not GitHubWebhookEvent.objects.exists()


@pytest.mark.django_db
def test_webhook_endpoint_stores_signed_payload_with_invalid_ids_as_failed(
    settings,
    monkeypatch,
):
    settings.GITHUB_WEBHOOK_SECRET = WEBHOOK_SECRET
    queued_event_ids = []
    monkeypatch.setattr(
        "apps.github_app.views.process_github_webhook_event.delay",
        lambda event_id: queued_event_ids.append(event_id),
    )

    response = post_webhook(
        payload={"installation": {"id": "not-an-int"}},
        event_name="push",
        delivery_id="invalid-payload-id",
    )

    event = GitHubWebhookEvent.objects.get(delivery_id="invalid-payload-id")
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_github_webhook_payload"
    assert event.status == GitHubWebhookEvent.Status.FAILED
    assert event.result["error"] == "invalid_github_webhook_payload"
    assert "installation.id" in event.last_error
    assert event.processed_at is not None
    assert queued_event_ids == []


@pytest.mark.django_db
def test_webhook_endpoint_requires_delivery_and_event_headers(settings):
    settings.GITHUB_WEBHOOK_SECRET = WEBHOOK_SECRET
    body = encode_payload({"zen": "missing headers"})

    response = APIClient().post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature_for(body),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "missing_github_webhook_header"
    assert not GitHubWebhookEvent.objects.exists()


@pytest.mark.django_db
def test_installation_created_syncs_state_audits_and_creates_first_scan(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    event = create_webhook_event(
        event_name="installation",
        payload={
            "action": "created",
            "installation": installation_payload(),
            "repositories": [repository_payload(3001, "api")],
        },
        delivery_id="installation-created",
    )

    process_stored_github_webhook_event(str(event.id))

    event.refresh_from_db()
    organization = CustomerOrganization.objects.get()
    installation = GitHubInstallation.objects.get()
    repository = ManagedRepository.objects.get()
    session = GardeningSession.objects.get()
    assert event.status == GitHubWebhookEvent.Status.PROCESSED
    assert organization.github_login == "acme"
    assert installation.github_installation_id == 2001
    assert repository.full_name == "acme/api"
    assert session.repository == repository
    assert session.trigger["type"] == "first_scan"
    assert session.trigger["source"] == "github_webhook"
    assert session.trigger["delivery_id"] == "installation-created"
    assert session.trigger["subject_type"] == "repository"
    assert session.trigger["subject_id"] == "3001"
    assert queued_sessions == [str(session.id)]
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.GITHUB_INSTALLATION_SYNCED,
        source="github_webhook",
    ).exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.MANAGED_REPOSITORY_SELECTED,
        source="github_webhook",
    ).exists()


@pytest.mark.django_db
def test_installation_repositories_added_and_removed_syncs_repository_state(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    organization = create_organization()
    installation = create_installation(organization)

    added_event = create_webhook_event(
        event_name="installation_repositories",
        payload={
            "action": "added",
            "installation": installation_payload(),
            "repositories_added": [repository_payload(3002, "web")],
        },
        delivery_id="repo-added",
    )
    process_stored_github_webhook_event(str(added_event.id))

    repository = ManagedRepository.objects.get(github_repository_id=3002)
    assert repository.is_active
    assert GardeningSession.objects.get(repository=repository).trigger["type"] == "first_scan"
    assert queued_sessions == [str(GardeningSession.objects.get().id)]

    removed_event = create_webhook_event(
        event_name="installation_repositories",
        payload={
            "action": "removed",
            "installation": installation_payload(),
            "repositories_removed": [repository_payload(3002, "web")],
        },
        delivery_id="repo-removed",
    )
    process_stored_github_webhook_event(str(removed_event.id))

    repository.refresh_from_db()
    installation.refresh_from_db()
    assert repository.unselected_at is not None
    assert installation.organization == organization
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.MANAGED_REPOSITORY_UNSELECTED,
        source="github_webhook",
    ).exists()


@pytest.mark.django_db
def test_push_webhook_creates_session_for_default_branch_only(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    repository = create_repository()
    default_event = create_webhook_event(
        event_name="push",
        payload=push_payload(repository, ref="refs/heads/main", after="abc123"),
        delivery_id="push-main",
    )
    feature_event = create_webhook_event(
        event_name="push",
        payload=push_payload(repository, ref="refs/heads/feature", after="def456"),
        delivery_id="push-feature",
    )

    process_stored_github_webhook_event(str(default_event.id))
    process_stored_github_webhook_event(str(feature_event.id))

    default_event.refresh_from_db()
    feature_event.refresh_from_db()
    session = GardeningSession.objects.get()
    assert default_event.status == GitHubWebhookEvent.Status.PROCESSED
    assert feature_event.status == GitHubWebhookEvent.Status.IGNORED
    assert session.trigger["type"] == "push"
    assert session.trigger["ref"] == "refs/heads/main"
    assert session.trigger["commit_sha"] == "abc123"
    assert queued_sessions == [str(session.id)]


@pytest.mark.django_db
def test_push_webhook_derives_n_commits_and_risky_module_sessions(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    repository = create_repository()
    # No constitution wired -> fallback: default protected segment "auth" and
    # default commit threshold (10). One commit touches a protected path; total
    # commit count crosses the threshold.
    commits = [{"added": [], "modified": ["src/auth/login.py"], "removed": []}]
    commits += [
        {"added": [], "modified": [f"src/feature_{i}.py"], "removed": []}
        for i in range(10)
    ]
    event = create_webhook_event(
        event_name="push",
        payload=push_payload(
            repository, ref="refs/heads/main", after="abc123", commits=commits
        ),
        delivery_id="push-derived-triggers",
    )

    process_stored_github_webhook_event(str(event.id))

    triggers = {
        session.trigger["type"]: session
        for session in GardeningSession.objects.filter(repository=repository)
    }
    assert set(triggers) == {"push", "n_commits", "risky_module"}
    assert "src/auth/login.py" in triggers["risky_module"].trigger["reason"]
    # Every derived session is enqueued to the worker.
    assert len(queued_sessions) == 3


@pytest.mark.django_db
def test_failed_session_enqueue_does_not_block_followup_webhook_session(monkeypatch):
    queued_sessions = []

    def flaky_delay(session_id: str):
        queued_sessions.append(session_id)
        if len(queued_sessions) == 1:
            raise RuntimeError("broker unavailable")
        return SimpleNamespace(id="task-2")

    monkeypatch.setattr("apps.triggers.service.run_gardening_session.delay", flaky_delay)
    repository = create_repository()
    first_event = create_webhook_event(
        event_name="push",
        payload=push_payload(repository, ref="refs/heads/main", after="abc123"),
        delivery_id="push-first-enqueue-failure",
    )
    second_event = create_webhook_event(
        event_name="push",
        payload=push_payload(repository, ref="refs/heads/main", after="def456"),
        delivery_id="push-followup-after-enqueue-failure",
    )

    first_result = process_stored_github_webhook_event(str(first_event.id))
    second_result = process_stored_github_webhook_event(str(second_event.id))

    first_event.refresh_from_db()
    second_event.refresh_from_db()
    failed_session = GardeningSession.objects.get(id=queued_sessions[0])
    queued_session = GardeningSession.objects.get(id=queued_sessions[1])
    assert first_result["status"] == GitHubWebhookEvent.Status.RECEIVED
    assert first_event.status == GitHubWebhookEvent.Status.RECEIVED
    assert first_event.last_error == "Session queue enqueue failed: broker unavailable"
    assert first_event.result == {
        "status": "retryable",
        "error": "Session queue enqueue failed: broker unavailable",
    }
    assert failed_session.status == GardeningSession.Status.FAILED
    assert failed_session.finished_at is not None
    assert failed_session.last_error == "Session queue enqueue failed: broker unavailable"
    assert failed_session.result["errors"] == [
        {"phase": "queue", "message": "Session queue enqueue failed: broker unavailable"}
    ]
    assert second_result["status"] == GitHubWebhookEvent.Status.PROCESSED
    assert second_event.status == GitHubWebhookEvent.Status.PROCESSED
    assert queued_session.status == GardeningSession.Status.QUEUED
    assert queued_session.task_id == "task-2"
    assert GardeningSession.objects.count() == 2
    assert queued_sessions == [str(failed_session.id), str(queued_session.id)]


@pytest.mark.django_db
def test_failed_session_enqueue_keeps_same_webhook_delivery_retryable(monkeypatch):
    queued_sessions = []

    def flaky_delay(session_id: str):
        queued_sessions.append(session_id)
        if len(queued_sessions) == 1:
            raise RuntimeError("broker unavailable")
        return SimpleNamespace(id="task-2")

    monkeypatch.setattr("apps.triggers.service.run_gardening_session.delay", flaky_delay)
    repository = create_repository()
    event = create_webhook_event(
        event_name="push",
        payload=push_payload(repository, ref="refs/heads/main", after="abc123"),
        delivery_id="push-retry-same-delivery",
    )

    first_result = process_stored_github_webhook_event(str(event.id))
    second_result = process_stored_github_webhook_event(str(event.id))

    event.refresh_from_db()
    failed_session = GardeningSession.objects.get(id=queued_sessions[0])
    queued_session = GardeningSession.objects.get(id=queued_sessions[1])
    assert first_result["status"] == GitHubWebhookEvent.Status.RECEIVED
    assert second_result["status"] == GitHubWebhookEvent.Status.PROCESSED
    assert event.status == GitHubWebhookEvent.Status.PROCESSED
    assert failed_session.status == GardeningSession.Status.FAILED
    assert queued_session.status == GardeningSession.Status.QUEUED
    assert queued_session.task_id == "task-2"
    assert GardeningSession.objects.count() == 2
    assert queued_sessions == [str(failed_session.id), str(queued_session.id)]


@pytest.mark.django_db
def test_pull_request_webhook_creates_session_for_open_actions(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    repository = create_repository()
    opened_event = create_webhook_event(
        event_name="pull_request",
        payload=pull_request_payload(repository, action="opened", number=42),
        delivery_id="pr-opened",
    )
    closed_event = create_webhook_event(
        event_name="pull_request",
        payload=pull_request_payload(repository, action="closed", number=42),
        delivery_id="pr-closed",
    )

    process_stored_github_webhook_event(str(opened_event.id))
    process_stored_github_webhook_event(str(closed_event.id))

    opened_event.refresh_from_db()
    closed_event.refresh_from_db()
    session = GardeningSession.objects.get()
    assert opened_event.status == GitHubWebhookEvent.Status.PROCESSED
    assert closed_event.status == GitHubWebhookEvent.Status.IGNORED
    assert session.trigger["type"] == "pr_opened"
    assert session.trigger["pull_request_number"] == 42
    assert queued_sessions == [str(session.id)]


@pytest.mark.django_db
def test_workflow_run_and_check_suite_create_sessions_only_for_failures(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    repository = create_repository()
    failed_workflow = create_webhook_event(
        event_name="workflow_run",
        payload=ci_payload(
            repository,
            key="workflow_run",
            conclusion="failure",
            identifier=901,
        ),
        delivery_id="workflow-failed",
    )
    successful_check = create_webhook_event(
        event_name="check_suite",
        payload=ci_payload(
            repository,
            key="check_suite",
            conclusion="success",
            identifier=902,
        ),
        delivery_id="check-success",
    )

    process_stored_github_webhook_event(str(failed_workflow.id))
    process_stored_github_webhook_event(str(successful_check.id))

    failed_workflow.refresh_from_db()
    successful_check.refresh_from_db()
    session = GardeningSession.objects.get()
    assert failed_workflow.status == GitHubWebhookEvent.Status.PROCESSED
    assert successful_check.status == GitHubWebhookEvent.Status.IGNORED
    assert session.trigger["type"] == "ci_failure"
    assert session.trigger["workflow_run_id"] == 901
    assert queued_sessions == [str(session.id)]


@pytest.mark.django_db
def test_active_session_dedupe_prevents_noisy_webhook_sessions(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    repository = create_repository()
    existing = GardeningSession.objects.create(
        repository=repository,
        trigger={
            "type": "push",
            "source": "github_webhook",
            "subject_type": "ref",
            "subject_id": "refs/heads/main",
        },
    )
    event = create_webhook_event(
        event_name="push",
        payload=push_payload(repository, ref="refs/heads/main", after="abc123"),
        delivery_id="push-deduped",
    )

    process_stored_github_webhook_event(str(event.id))

    event.refresh_from_db()
    assert event.status == GitHubWebhookEvent.Status.PROCESSED
    assert event.result["sessions_created"] == [
        {
            "gardening_session_id": str(existing.id),
            "status": GardeningSession.Status.QUEUED,
            "deduped": True,
        }
    ]
    assert GardeningSession.objects.count() == 1
    assert queued_sessions == []


@pytest.mark.django_db
def test_processing_skips_already_claimed_webhook_event(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    repository = create_repository()
    event = create_webhook_event(
        event_name="push",
        payload=push_payload(repository, ref="refs/heads/main", after="abc123"),
        delivery_id="push-processing",
    )
    event.status = GitHubWebhookEvent.Status.PROCESSING
    event.save(update_fields=["status", "updated_at"])

    result = process_stored_github_webhook_event(str(event.id))

    event.refresh_from_db()
    assert result["status"] == GitHubWebhookEvent.Status.PROCESSING
    assert event.status == GitHubWebhookEvent.Status.PROCESSING
    assert GardeningSession.objects.count() == 0
    assert queued_sessions == []


@pytest.mark.django_db
def test_push_webhook_ignores_repository_from_different_installation(monkeypatch):
    queued_sessions = patch_session_enqueue(monkeypatch)
    repository = create_repository()
    other_organization = create_organization(
        account_id=1002,
        login="other",
        name="Other",
    )
    other_installation = create_installation(
        other_organization,
        github_installation_id=2002,
    )
    payload = push_payload(repository, ref="refs/heads/main", after="abc123")
    payload["installation"] = {"id": other_installation.github_installation_id}
    event = create_webhook_event(
        event_name="push",
        payload=payload,
        delivery_id="push-wrong-installation",
    )

    process_stored_github_webhook_event(str(event.id))

    event.refresh_from_db()
    assert event.status == GitHubWebhookEvent.Status.IGNORED
    assert event.result["reason"] == "repository_not_found_or_inactive"
    assert GardeningSession.objects.count() == 0
    assert queued_sessions == []


@pytest.mark.django_db
def test_repository_deleted_webhook_ignores_repository_from_different_installation():
    repository = create_repository()
    other_organization = create_organization(
        account_id=1002,
        login="other",
        name="Other",
    )
    other_installation = create_installation(
        other_organization,
        github_installation_id=2002,
    )
    event = create_webhook_event(
        event_name="repository",
        payload={
            "action": "deleted",
            "installation": {"id": other_installation.github_installation_id},
            "repository": repository_payload(repository.github_repository_id, repository.name),
        },
        delivery_id="repo-delete-wrong-installation",
    )

    process_stored_github_webhook_event(str(event.id))

    event.refresh_from_db()
    repository.refresh_from_db()
    assert event.status == GitHubWebhookEvent.Status.IGNORED
    assert event.result["reason"] == "repository_not_found"
    assert repository.deleted_at is None


@pytest.mark.django_db
def test_processing_failure_is_visible_on_webhook_event():
    event = create_webhook_event(
        event_name="installation",
        payload={"action": "created", "installation": {"id": 2001}},
        delivery_id="bad-installation-payload",
    )

    result = process_stored_github_webhook_event(str(event.id))

    event.refresh_from_db()
    assert result["status"] == GitHubWebhookEvent.Status.FAILED
    assert event.status == GitHubWebhookEvent.Status.FAILED
    assert event.last_error == "GitHub installation account was invalid."
    assert event.result["status"] == GitHubWebhookEvent.Status.FAILED
    assert event.processed_at is not None


def post_webhook(
    *,
    payload: dict,
    event_name: str,
    delivery_id: str = "delivery",
    signature: str | None = "auto",
):
    body = encode_payload(payload)
    headers = {
        "HTTP_X_GITHUB_DELIVERY": delivery_id,
        "HTTP_X_GITHUB_EVENT": event_name,
    }
    if signature == "auto":
        headers["HTTP_X_HUB_SIGNATURE_256"] = signature_for(body)
    elif signature is not None:
        headers["HTTP_X_HUB_SIGNATURE_256"] = signature
    return APIClient().post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        **headers,
    )


def encode_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def signature_for(body: bytes) -> str:
    return "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def create_webhook_event(
    *,
    event_name: str,
    payload: dict,
    delivery_id: str,
) -> GitHubWebhookEvent:
    return ingest_github_webhook_delivery(
        delivery_id=delivery_id,
        event_name=event_name,
        payload=payload,
    ).event


def patch_session_enqueue(monkeypatch):
    queued_sessions = []

    def fake_delay(session_id: str):
        queued_sessions.append(session_id)
        return SimpleNamespace(id=f"task-{len(queued_sessions)}")

    monkeypatch.setattr("apps.triggers.service.run_gardening_session.delay", fake_delay)
    return queued_sessions


def create_organization(
    *,
    account_id: int = 1001,
    login: str = "acme",
    name: str = "Acme",
) -> CustomerOrganization:
    return CustomerOrganization.objects.create(
        name=name,
        github_account_id=account_id,
        github_login=login,
        github_account_type=CustomerOrganization.GitHubAccountType.ORGANIZATION,
    )


def create_installation(
    organization: CustomerOrganization | None = None,
    *,
    github_installation_id: int = 2001,
) -> GitHubInstallation:
    organization = organization or create_organization()
    return GitHubInstallation.objects.create(
        organization=organization,
        github_installation_id=github_installation_id,
        github_account_id=organization.github_account_id,
        github_account_login=organization.github_login,
        github_account_type=GitHubInstallation.GitHubAccountType.ORGANIZATION,
        repository_selection=GitHubInstallation.RepositorySelection.SELECTED,
        permissions={"metadata": "read", "contents": "read"},
        events=["installation", "installation_repositories", "push", "pull_request"],
        html_url="https://github.com/organizations/acme/settings/installations/2001",
    )


def create_repository(
    *,
    identifier: int = 3001,
    name: str = "api",
    installation: GitHubInstallation | None = None,
) -> ManagedRepository:
    installation = installation or create_installation()
    return ManagedRepository.objects.create(
        organization=installation.organization,
        github_installation=installation,
        github_repository_id=identifier,
        name=name,
        full_name=f"acme/{name}",
        owner_login="acme",
        private=True,
        default_branch="main",
        html_url=f"https://github.com/acme/{name}",
    )


def installation_payload() -> dict:
    return {
        "id": 2001,
        "account": {
            "id": 1001,
            "login": "acme",
            "type": "Organization",
        },
        "repository_selection": "selected",
        "permissions": {"metadata": "read", "contents": "read"},
        "events": ["installation", "installation_repositories", "push", "pull_request"],
        "html_url": "https://github.com/organizations/acme/settings/installations/2001",
        "suspended_at": None,
    }


def repository_payload(identifier: int, name: str) -> dict:
    return {
        "id": identifier,
        "name": name,
        "full_name": f"acme/{name}",
        "owner": {"login": "acme"},
        "private": True,
        "default_branch": "main",
        "html_url": f"https://github.com/acme/{name}",
    }


def push_payload(
    repository: ManagedRepository,
    *,
    ref: str,
    after: str,
    commits: list[dict] | None = None,
) -> dict:
    return {
        "ref": ref,
        "before": "0000000",
        "after": after,
        "deleted": False,
        "commits": commits if commits is not None else [],
        "installation": {"id": repository.github_installation.github_installation_id},
        "repository": repository_payload(repository.github_repository_id, repository.name),
    }


def pull_request_payload(
    repository: ManagedRepository,
    *,
    action: str,
    number: int,
) -> dict:
    return {
        "action": action,
        "number": number,
        "installation": {"id": repository.github_installation.github_installation_id},
        "repository": repository_payload(repository.github_repository_id, repository.name),
        "pull_request": {"number": number},
    }


def ci_payload(
    repository: ManagedRepository,
    *,
    key: str,
    conclusion: str,
    identifier: int,
) -> dict:
    return {
        "action": "completed",
        "installation": {"id": repository.github_installation.github_installation_id},
        "repository": repository_payload(repository.github_repository_id, repository.name),
        key: {
            "id": identifier,
            "status": "completed",
            "conclusion": conclusion,
        },
    }
