from __future__ import annotations

from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import UTC
from typing import Any
from urllib.parse import urlencode, quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import CustomerOrganization, Membership
from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError, GitHubAppClient
from apps.github_app.models import GitHubInstallation, GitHubWebhookEvent
from apps.github_app.state import create_install_state, load_install_state
from apps.repositories.models import ManagedRepository
from apps.triggers.service import (
    SessionEnqueueError,
    enqueue_session_for_trigger,
    evaluate_push_triggers,
)


WEBHOOK_AUDIT_SOURCE = "github_webhook"
PR_TRIGGER_ACTIONS = {"opened", "reopened", "synchronize"}
FAILED_CI_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "startup_failure",
    "timed_out",
}


class GitHubAppOnboardingError(Exception):
    code = "github_app_onboarding_error"


class MissingCallbackParameterError(GitHubAppOnboardingError):
    code = "missing_required_callback_parameter"


class InvalidInstallStateError(GitHubAppOnboardingError):
    code = "invalid_install_state"


class GitHubOAuthError(GitHubAppOnboardingError):
    code = "github_oauth_failed"


class GitHubInstallationVerificationError(GitHubAppOnboardingError):
    code = "github_installation_verification_failed"


class GitHubInstallerAuthorizationError(GitHubAppOnboardingError):
    code = "github_installer_authorization_failed"


class GitHubInstallationSyncError(GitHubAppOnboardingError):
    code = "github_installation_sync_failed"


class GitHubWebhookPayloadError(Exception):
    code = "invalid_github_webhook_payload"


@dataclass(frozen=True)
class InstallationCallbackResult:
    status: str
    user: Any | None = None
    organization: CustomerOrganization | None = None
    repository_count: int = 0


@dataclass(frozen=True)
class GitHubWebhookIngestResult:
    event: GitHubWebhookEvent
    created: bool
    error_code: str = ""


@dataclass(frozen=True)
class RepositorySyncResult:
    repository_count: int
    newly_selected_repositories: list[ManagedRepository]


def build_installation_start_url(
    session: MutableMapping[str, Any] | None = None,
) -> str:
    app_slug = settings.GITHUB_APP_SLUG.strip().strip("/")
    if not app_slug:
        raise ImproperlyConfigured("GITHUB_APP_SLUG is required.")

    query = urlencode({"state": create_install_state(session)})
    web_base_url = settings.GITHUB_WEB_BASE_URL.rstrip("/")
    return f"{web_base_url}/apps/{quote(app_slug)}/installations/new?{query}"


def complete_installation_callback(
    *,
    code: str | None,
    state: str | None,
    installation_id: str | int | None,
    setup_action: str | None,
    client: GitHubAppClient | None = None,
    state_loader: Callable[[str], dict[str, Any]] = load_install_state,
) -> InstallationCallbackResult:
    if not state:
        raise MissingCallbackParameterError("Missing state.")
    try:
        state_loader(state)
    except signing.BadSignature as exc:
        raise InvalidInstallStateError("Invalid install state.") from exc

    if setup_action == "request":
        return InstallationCallbackResult(status="pending")

    if not code or installation_id in (None, ""):
        raise MissingCallbackParameterError("Missing code or installation_id.")

    github_installation_id = _parse_installation_id(installation_id)
    github_client = client or GitHubAppClient()

    try:
        user_token = github_client.exchange_oauth_code(code)
        github_user = github_client.get_authenticated_user(user_token)
    except (GitHubAPIError, ImproperlyConfigured) as exc:
        raise GitHubOAuthError("GitHub OAuth failed.") from exc

    try:
        github_client.list_user_installation_repositories(
            user_token,
            github_installation_id,
        )
    except GitHubAPIError as exc:
        raise GitHubInstallationVerificationError(
            "GitHub user cannot access the installation."
        ) from exc

    try:
        installation_payload = github_client.get_installation(github_installation_id)
        _verify_installer_authority(
            github_client=github_client,
            user_token=user_token,
            github_user=github_user,
            installation_payload=installation_payload,
        )
        installation_token = github_client.create_installation_token(
            github_installation_id
        )
        repository_payloads = github_client.list_installation_repositories(
            installation_token
        )
    except (GitHubAPIError, ImproperlyConfigured) as exc:
        raise GitHubInstallationSyncError("GitHub installation sync failed.") from exc

    return sync_installation_from_github_payloads(
        github_user=github_user,
        installation_payload=installation_payload,
        repository_payloads=repository_payloads,
    )


def sync_installation_from_github_payloads(
    *,
    github_user: dict[str, Any],
    installation_payload: dict[str, Any],
    repository_payloads: list[dict[str, Any]],
) -> InstallationCallbackResult:
    with transaction.atomic():
        user = _upsert_user(github_user)
        organization = _upsert_organization(installation_payload)
        _upsert_owner_membership(user, organization)
        installation = _upsert_installation(organization, installation_payload)
        repository_sync = _sync_repositories(
            actor=user,
            organization=organization,
            installation=installation,
            repository_payloads=repository_payloads,
        )
        AuditEvent.objects.create(
            actor=user,
            organization=organization,
            github_installation=installation,
            event_type=AuditEvent.EventType.GITHUB_INSTALLATION_SYNCED,
            metadata={
                "github_installation_id": installation.github_installation_id,
                "repository_count": repository_sync.repository_count,
            },
        )

    return InstallationCallbackResult(
        status="installed",
        user=user,
        organization=organization,
        repository_count=repository_sync.repository_count,
    )


def ingest_github_webhook_delivery(
    *,
    delivery_id: str,
    event_name: str,
    payload: dict[str, Any],
) -> GitHubWebhookIngestResult:
    try:
        defaults = {
            "event": event_name,
            "action": str(payload.get("action") or ""),
            "github_installation_id": _payload_installation_id(payload),
            "github_repository_id": _payload_repository_id(payload),
            "repository_full_name": _payload_repository_full_name(payload),
            "payload": payload,
        }
    except GitHubWebhookPayloadError as exc:
        return _store_failed_webhook_delivery(
            delivery_id=delivery_id,
            event_name=event_name,
            payload=payload,
            error=str(exc),
        )

    try:
        event, created = GitHubWebhookEvent.objects.get_or_create(
            delivery_id=delivery_id,
            defaults=defaults,
        )
    except IntegrityError:
        event = GitHubWebhookEvent.objects.get(delivery_id=delivery_id)
        created = False

    return GitHubWebhookIngestResult(event=event, created=created)


def process_stored_github_webhook_event(webhook_event_id: str) -> dict[str, str]:
    with transaction.atomic():
        event = GitHubWebhookEvent.objects.select_for_update().get(id=webhook_event_id)
        if event.status in (
            GitHubWebhookEvent.Status.PROCESSING,
            GitHubWebhookEvent.Status.PROCESSED,
            GitHubWebhookEvent.Status.IGNORED,
            GitHubWebhookEvent.Status.FAILED,
        ):
            return {"webhook_event_id": str(event.id), "status": event.status}

        event.status = GitHubWebhookEvent.Status.PROCESSING
        event.last_error = ""
        event.save(update_fields=["status", "last_error", "updated_at"])

    try:
        result = _route_github_webhook_event(event)
    except SessionEnqueueError as exc:
        event.status = GitHubWebhookEvent.Status.RECEIVED
        event.last_error = str(exc)
        event.processed_at = timezone.now()
        event.result = {
            "status": "retryable",
            "error": str(exc),
        }
        event.save(
            update_fields=[
                "status",
                "last_error",
                "processed_at",
                "result",
                "updated_at",
            ]
        )
        return {"webhook_event_id": str(event.id), "status": event.status}
    except Exception as exc:
        event.status = GitHubWebhookEvent.Status.FAILED
        event.last_error = str(exc)
        event.processed_at = timezone.now()
        event.result = {
            "status": GitHubWebhookEvent.Status.FAILED,
            "error": str(exc),
        }
        event.save(
            update_fields=[
                "status",
                "last_error",
                "processed_at",
                "result",
                "updated_at",
            ]
        )
        return {"webhook_event_id": str(event.id), "status": event.status}

    event.status = result["status"]
    event.result = result
    event.processed_at = timezone.now()
    event.last_error = ""
    event.save(
        update_fields=[
            "status",
            "result",
            "processed_at",
            "last_error",
            "updated_at",
        ]
    )
    return {"webhook_event_id": str(event.id), "status": event.status}


def _route_github_webhook_event(event: GitHubWebhookEvent) -> dict[str, Any]:
    if event.event == "ping":
        return _ignored_result("ping")
    if event.event == "installation":
        return _process_installation_webhook(event)
    if event.event == "installation_repositories":
        return _process_installation_repositories_webhook(event)
    if event.event == "repository":
        return _process_repository_webhook(event)
    if event.event == "push":
        return _process_push_webhook(event)
    if event.event == "pull_request":
        return _process_pull_request_webhook(event)
    if event.event in {"workflow_run", "check_suite"}:
        return _process_ci_webhook(event)
    return _ignored_result("unsupported_event", event=event.event)


def _process_installation_webhook(event: GitHubWebhookEvent) -> dict[str, Any]:
    action = event.action
    if action in {"created", "updated"}:
        repository_payloads = _optional_payload_list(event.payload, "repositories")
        with transaction.atomic():
            organization = _upsert_organization(event.payload["installation"])
            installation = _upsert_installation(
                organization,
                event.payload["installation"],
            )
            repository_sync = RepositorySyncResult(
                repository_count=installation.managed_repositories.count(),
                newly_selected_repositories=[],
            )
            if repository_payloads is not None:
                repository_sync = _sync_repositories(
                    actor=None,
                    organization=organization,
                    installation=installation,
                    repository_payloads=repository_payloads,
                    audit_source=WEBHOOK_AUDIT_SOURCE,
                )
            AuditEvent.objects.create(
                actor=None,
                organization=organization,
                github_installation=installation,
                event_type=AuditEvent.EventType.GITHUB_INSTALLATION_SYNCED,
                source=WEBHOOK_AUDIT_SOURCE,
                metadata={
                    "action": action,
                    "github_installation_id": installation.github_installation_id,
                    "repository_count": repository_sync.repository_count,
                },
            )

        sessions = [
            _create_first_scan_session(repository, event)
            for repository in repository_sync.newly_selected_repositories
        ]
        return _processed_result(
            action=action,
            repository_count=repository_sync.repository_count,
            sessions_created=sessions,
        )

    if action == "deleted":
        installation = GitHubInstallation.objects.filter(
            github_installation_id=event.github_installation_id
        ).first()
        if installation is None:
            return _ignored_result("installation_not_found")

        unselected_count = _mark_installation_deleted(installation)
        return _processed_result(
            action=action,
            github_installation_id=installation.github_installation_id,
            repositories_unselected=unselected_count,
        )

    return _ignored_result("unsupported_installation_action", action=action)


def _process_installation_repositories_webhook(
    event: GitHubWebhookEvent,
) -> dict[str, Any]:
    action = event.action
    with transaction.atomic():
        organization = _upsert_organization(event.payload["installation"])
        installation = _upsert_installation(organization, event.payload["installation"])

        if action == "added":
            repositories = _payload_list(event.payload, "repositories_added")
            newly_selected = _select_repository_payloads(
                actor=None,
                organization=organization,
                installation=installation,
                repository_payloads=repositories,
                audit_source=WEBHOOK_AUDIT_SOURCE,
            )
            AuditEvent.objects.create(
                actor=None,
                organization=organization,
                github_installation=installation,
                event_type=AuditEvent.EventType.GITHUB_INSTALLATION_SYNCED,
                source=WEBHOOK_AUDIT_SOURCE,
                metadata={
                    "action": action,
                    "github_installation_id": installation.github_installation_id,
                    "repositories_added": len(repositories),
                },
            )
        elif action == "removed":
            repositories = _payload_list(event.payload, "repositories_removed")
            unselected_count = _unselect_repository_payloads(
                actor=None,
                installation=installation,
                repository_payloads=repositories,
                audit_source=WEBHOOK_AUDIT_SOURCE,
            )
            AuditEvent.objects.create(
                actor=None,
                organization=organization,
                github_installation=installation,
                event_type=AuditEvent.EventType.GITHUB_INSTALLATION_SYNCED,
                source=WEBHOOK_AUDIT_SOURCE,
                metadata={
                    "action": action,
                    "github_installation_id": installation.github_installation_id,
                    "repositories_removed": unselected_count,
                },
            )
            return _processed_result(
                action=action,
                repositories_unselected=unselected_count,
            )
        else:
            return _ignored_result(
                "unsupported_installation_repositories_action",
                action=action,
            )

    sessions = [_create_first_scan_session(repository, event) for repository in newly_selected]
    return _processed_result(
        action=action,
        repositories_selected=len(newly_selected),
        sessions_created=sessions,
    )


def _process_repository_webhook(event: GitHubWebhookEvent) -> dict[str, Any]:
    action = event.action
    if action == "deleted":
        repository = _active_repository_for_event(event)
        if repository is None:
            return _ignored_result("repository_not_found")

        repository.deleted_at = timezone.now()
        repository.save(update_fields=["deleted_at", "updated_at"])
        AuditEvent.objects.create(
            actor=None,
            organization=repository.organization,
            github_installation=repository.github_installation,
            repository=repository,
            event_type=AuditEvent.EventType.MANAGED_REPOSITORY_UNSELECTED,
            source=WEBHOOK_AUDIT_SOURCE,
            metadata={
                "action": action,
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
            },
        )
        return _processed_result(action=action, repository_id=str(repository.id))

    if action not in {"created", "edited", "renamed", "publicized", "privatized"}:
        return _ignored_result("unsupported_repository_action", action=action)

    installation = _active_installation_for_event(event)
    if installation is None:
        return _ignored_result("installation_not_found")

    repository = _upsert_repository(
        organization=installation.organization,
        installation=installation,
        payload=event.payload["repository"],
        selected_at=timezone.now(),
    )
    sessions = []
    if repository._gardener_was_selected:
        AuditEvent.objects.create(
            actor=None,
            organization=installation.organization,
            github_installation=installation,
            repository=repository,
            event_type=AuditEvent.EventType.MANAGED_REPOSITORY_SELECTED,
            source=WEBHOOK_AUDIT_SOURCE,
            metadata={
                "action": action,
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
            },
        )
        sessions.append(_create_first_scan_session(repository, event))

    return _processed_result(
        action=action,
        repository_id=str(repository.id),
        sessions_created=sessions,
    )


def _process_push_webhook(event: GitHubWebhookEvent) -> dict[str, Any]:
    repository = _active_repository_for_event(event)
    if repository is None:
        return _ignored_result("repository_not_found_or_inactive")

    ref = str(event.payload.get("ref") or "")
    default_ref = f"refs/heads/{repository.default_branch}"
    if event.payload.get("deleted") is True:
        return _ignored_result("deleted_push", ref=ref)
    if ref != default_ref:
        return _ignored_result("non_default_branch_push", ref=ref)

    session = _create_or_get_webhook_session(
        repository=repository,
        event=event,
        trigger_type="push",
        subject_type="ref",
        subject_id=ref,
        extra={
            "ref": ref,
            "commit_sha": event.payload.get("after") or "",
        },
    )
    sessions = [session]
    sessions.extend(
        evaluate_push_triggers(
            repository=repository,
            ref=ref,
            payload=event.payload,
            base_trigger_extra={
                "source": WEBHOOK_AUDIT_SOURCE,
                "delivery_id": event.delivery_id,
                "event": event.event,
                "action": event.action,
            },
        )
    )
    return _processed_result(sessions_created=sessions)


def _process_pull_request_webhook(event: GitHubWebhookEvent) -> dict[str, Any]:
    if event.action not in PR_TRIGGER_ACTIONS:
        return _ignored_result("unsupported_pull_request_action", action=event.action)

    repository = _active_repository_for_event(event)
    if repository is None:
        return _ignored_result("repository_not_found_or_inactive")

    pull_request = event.payload.get("pull_request") or {}
    pull_request_number = event.payload.get("number") or pull_request.get("number")
    if pull_request_number is None:
        return _ignored_result("missing_pull_request_number")

    session = _create_or_get_webhook_session(
        repository=repository,
        event=event,
        trigger_type="pr_opened",
        subject_type="pull_request",
        subject_id=str(pull_request_number),
        extra={"pull_request_number": int(pull_request_number)},
    )
    return _processed_result(sessions_created=[session])


def _process_ci_webhook(event: GitHubWebhookEvent) -> dict[str, Any]:
    repository = _active_repository_for_event(event)
    if repository is None:
        return _ignored_result("repository_not_found_or_inactive")

    ci_payload = event.payload.get(event.event) or {}
    if ci_payload.get("status") not in (None, "completed"):
        return _ignored_result("ci_not_completed", status=ci_payload.get("status"))

    conclusion = ci_payload.get("conclusion")
    if conclusion not in FAILED_CI_CONCLUSIONS:
        return _ignored_result("ci_not_failed", conclusion=conclusion)

    subject_id = str(ci_payload.get("id") or "")
    if not subject_id:
        return _ignored_result("missing_ci_subject_id")

    session = _create_or_get_webhook_session(
        repository=repository,
        event=event,
        trigger_type="ci_failure",
        subject_type=event.event,
        subject_id=subject_id,
        extra={f"{event.event}_id": int(subject_id)},
    )
    return _processed_result(sessions_created=[session])


def _parse_installation_id(installation_id: str | int) -> int:
    try:
        parsed = int(installation_id)
    except (TypeError, ValueError) as exc:
        raise MissingCallbackParameterError("Invalid installation_id.") from exc
    if parsed <= 0:
        raise MissingCallbackParameterError("Invalid installation_id.")
    return parsed


def _upsert_user(github_user: dict[str, Any]):
    User = get_user_model()
    github_user_id = int(github_user["id"])
    github_login = str(github_user.get("login") or f"github-{github_user_id}")
    email = github_user.get("email") or _synthetic_github_email(github_user_id)
    normalized_email = User.objects.normalize_email(email)

    user = User.objects.filter(github_user_id=github_user_id).first()
    if user is None:
        email_owner = User.objects.filter(email=normalized_email).first()
        if email_owner and email_owner.github_user_id not in (None, github_user_id):
            normalized_email = _synthetic_github_email(github_user_id)
            email_owner = User.objects.filter(email=normalized_email).first()
        user = email_owner
    else:
        email_owner = User.objects.filter(email=normalized_email).exclude(pk=user.pk).first()
        if email_owner:
            normalized_email = _synthetic_github_email(github_user_id)

    defaults = {
        "email": normalized_email,
        "github_user_id": github_user_id,
        "github_login": github_login,
        "github_avatar_url": github_user.get("avatar_url") or "",
        "is_active": True,
    }

    if user is None:
        return User.objects.create_user(password=None, **defaults)

    for field, value in defaults.items():
        setattr(user, field, value)
    user.save(update_fields=[*defaults.keys(), "updated_at"])
    return user


def _synthetic_github_email(github_user_id: int) -> str:
    return f"github-{github_user_id}@users.codebase-gardener.local"


def _upsert_organization(
    installation_payload: dict[str, Any],
) -> CustomerOrganization:
    account = _installation_account(installation_payload)
    account_id = int(account["id"])
    account_login = str(account["login"])
    account_type = _github_account_type(account)

    organization, _created = CustomerOrganization.objects.update_or_create(
        github_account_id=account_id,
        defaults={
            "name": account.get("name") or account_login,
            "github_login": account_login,
            "github_account_type": account_type,
            "deactivated_at": None,
        },
    )
    return organization


def _verify_installer_authority(
    *,
    github_client: GitHubAppClient,
    user_token: str,
    github_user: dict[str, Any],
    installation_payload: dict[str, Any],
) -> None:
    account = _installation_account(installation_payload)
    account_type = _github_account_type(account)
    if account_type == CustomerOrganization.GitHubAccountType.USER:
        if int(account["id"]) != int(github_user["id"]):
            raise GitHubInstallerAuthorizationError(
                "GitHub user does not own this personal account installation."
            )
        return

    github_login = str(github_user.get("login") or "")
    org_login = str(account["login"])
    if not github_login:
        raise GitHubInstallerAuthorizationError("GitHub user login was missing.")

    try:
        membership = github_client.get_organization_membership(
            user_token,
            org_login=org_login,
            username=github_login,
        )
    except GitHubAPIError as exc:
        raise GitHubInstallerAuthorizationError(
            "GitHub installer organization membership could not be verified."
        ) from exc

    if membership.get("state") != "active" or membership.get("role") != "admin":
        raise GitHubInstallerAuthorizationError(
            "GitHub installer must be an active organization admin."
        )


def _upsert_owner_membership(user: Any, organization: CustomerOrganization) -> Membership:
    membership = Membership.objects.filter(
        user=user,
        organization=organization,
        deactivated_at__isnull=True,
    ).first()

    if membership is None:
        return Membership.objects.create(
            user=user,
            organization=organization,
            role=Membership.Role.OWNER,
        )

    if membership.role != Membership.Role.OWNER:
        membership.role = Membership.Role.OWNER
        membership.save(update_fields=["role", "updated_at"])
    return membership


def _upsert_installation(
    organization: CustomerOrganization,
    installation_payload: dict[str, Any],
) -> GitHubInstallation:
    account = _installation_account(installation_payload)
    github_account_type = _github_account_type(account)
    repository_selection = installation_payload.get(
        "repository_selection",
        GitHubInstallation.RepositorySelection.SELECTED,
    )

    installation, _created = GitHubInstallation.objects.update_or_create(
        github_installation_id=int(installation_payload["id"]),
        defaults={
            "organization": organization,
            "github_account_id": int(account["id"]),
            "github_account_login": str(account["login"]),
            "github_account_type": github_account_type,
            "repository_selection": repository_selection,
            "permissions": installation_payload.get("permissions") or {},
            "events": installation_payload.get("events") or [],
            "html_url": installation_payload.get("html_url") or "",
            "suspended_at": _parse_github_datetime(
                installation_payload.get("suspended_at")
            ),
            "deleted_at": None,
        },
    )
    return installation


def _sync_repositories(
    *,
    actor: Any,
    organization: CustomerOrganization,
    installation: GitHubInstallation,
    repository_payloads: list[dict[str, Any]],
    audit_source: str = "github_app_oauth_callback",
) -> RepositorySyncResult:
    now = timezone.now()
    granted_ids: set[int] = set()
    newly_selected = _select_repository_payloads(
        actor=actor,
        organization=organization,
        installation=installation,
        repository_payloads=repository_payloads,
        audit_source=audit_source,
        selected_at=now,
    )

    for payload in repository_payloads:
        granted_ids.add(int(payload["id"]))

    stale_repositories = ManagedRepository.objects.filter(
        github_installation=installation,
        unselected_at__isnull=True,
        deleted_at__isnull=True,
    ).exclude(github_repository_id__in=granted_ids)

    for repository in stale_repositories:
        repository.unselected_at = now
        repository.save(update_fields=["unselected_at", "updated_at"])
        AuditEvent.objects.create(
            actor=actor,
            organization=organization,
            github_installation=installation,
            repository=repository,
            event_type=AuditEvent.EventType.MANAGED_REPOSITORY_UNSELECTED,
            source=audit_source,
            metadata={
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
            },
        )

    return RepositorySyncResult(
        repository_count=len(granted_ids),
        newly_selected_repositories=newly_selected,
    )


def _select_repository_payloads(
    *,
    actor: Any,
    organization: CustomerOrganization,
    installation: GitHubInstallation,
    repository_payloads: list[dict[str, Any]],
    audit_source: str,
    selected_at=None,
) -> list[ManagedRepository]:
    selected_at = selected_at or timezone.now()
    newly_selected = []
    for payload in repository_payloads:
        repository = _upsert_repository(
            organization=organization,
            installation=installation,
            payload=payload,
            selected_at=selected_at,
        )
        if repository._gardener_was_selected:
            newly_selected.append(repository)
            AuditEvent.objects.create(
                actor=actor,
                organization=organization,
                github_installation=installation,
                repository=repository,
                event_type=AuditEvent.EventType.MANAGED_REPOSITORY_SELECTED,
                source=audit_source,
                metadata={
                    "github_repository_id": repository.github_repository_id,
                    "full_name": repository.full_name,
                },
            )
    return newly_selected


def _unselect_repository_payloads(
    *,
    actor: Any,
    installation: GitHubInstallation,
    repository_payloads: list[dict[str, Any]],
    audit_source: str,
) -> int:
    count = 0
    now = timezone.now()
    for payload in repository_payloads:
        repository = ManagedRepository.objects.filter(
            github_installation=installation,
            github_repository_id=int(payload["id"]),
            unselected_at__isnull=True,
            deleted_at__isnull=True,
        ).first()
        if repository is None:
            continue
        repository.unselected_at = now
        repository.save(update_fields=["unselected_at", "updated_at"])
        count += 1
        AuditEvent.objects.create(
            actor=actor,
            organization=repository.organization,
            github_installation=installation,
            repository=repository,
            event_type=AuditEvent.EventType.MANAGED_REPOSITORY_UNSELECTED,
            source=audit_source,
            metadata={
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
            },
        )
    return count


def _upsert_repository(
    *,
    organization: CustomerOrganization,
    installation: GitHubInstallation,
    payload: dict[str, Any],
    selected_at,
) -> ManagedRepository:
    github_repository_id = int(payload["id"])
    owner = payload.get("owner") or {}
    full_name = str(payload.get("full_name") or "")
    owner_login = owner.get("login") or full_name.split("/", 1)[0]

    repository = ManagedRepository.objects.filter(
        github_repository_id=github_repository_id
    ).first()
    was_selected = repository is None or repository.unselected_at or repository.deleted_at

    defaults = {
        "organization": organization,
        "github_installation": installation,
        "name": payload.get("name") or full_name.rsplit("/", 1)[-1],
        "full_name": full_name,
        "owner_login": owner_login,
        "private": bool(payload.get("private", True)),
        "default_branch": payload.get("default_branch") or "",
        "html_url": payload.get("html_url") or "",
        "unselected_at": None,
        "deleted_at": None,
    }

    if repository is None:
        repository = ManagedRepository.objects.create(
            github_repository_id=github_repository_id,
            selected_at=selected_at,
            **defaults,
        )
    else:
        for field, value in defaults.items():
            setattr(repository, field, value)
        if was_selected:
            repository.selected_at = selected_at
        repository.save(update_fields=[*defaults.keys(), "selected_at", "updated_at"])

    repository._gardener_was_selected = bool(was_selected)
    return repository


def _installation_account(installation_payload: dict[str, Any]) -> dict[str, Any]:
    account = installation_payload.get("account")
    if not isinstance(account, dict) or "id" not in account or "login" not in account:
        raise GitHubInstallationSyncError("GitHub installation account was invalid.")
    return account


def _github_account_type(account: dict[str, Any]) -> str:
    if account.get("type") == "Organization":
        return CustomerOrganization.GitHubAccountType.ORGANIZATION
    if account.get("type") == "User":
        return CustomerOrganization.GitHubAccountType.USER
    raise GitHubInstallationSyncError("GitHub account type was invalid.")


def _parse_github_datetime(value: Any):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone=UTC)
    return parsed


def _mark_installation_deleted(installation: GitHubInstallation) -> int:
    now = timezone.now()
    installation.deleted_at = now
    installation.save(update_fields=["deleted_at", "updated_at"])

    repositories = ManagedRepository.objects.filter(
        github_installation=installation,
        unselected_at__isnull=True,
        deleted_at__isnull=True,
    )
    count = 0
    for repository in repositories:
        repository.unselected_at = now
        repository.save(update_fields=["unselected_at", "updated_at"])
        count += 1
        AuditEvent.objects.create(
            actor=None,
            organization=repository.organization,
            github_installation=installation,
            repository=repository,
            event_type=AuditEvent.EventType.MANAGED_REPOSITORY_UNSELECTED,
            source=WEBHOOK_AUDIT_SOURCE,
            metadata={
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
            },
        )

    AuditEvent.objects.create(
        actor=None,
        organization=installation.organization,
        github_installation=installation,
        event_type=AuditEvent.EventType.GITHUB_INSTALLATION_SYNCED,
        source=WEBHOOK_AUDIT_SOURCE,
        metadata={
            "action": "deleted",
            "github_installation_id": installation.github_installation_id,
            "repositories_unselected": count,
        },
    )
    return count


def _create_first_scan_session(
    repository: ManagedRepository,
    event: GitHubWebhookEvent,
) -> dict[str, Any]:
    return _create_or_get_webhook_session(
        repository=repository,
        event=event,
        trigger_type="first_scan",
        subject_type="repository",
        subject_id=str(repository.github_repository_id),
        extra={},
    )


def _create_or_get_webhook_session(
    *,
    repository: ManagedRepository,
    event: GitHubWebhookEvent,
    trigger_type: str,
    subject_type: str,
    subject_id: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return enqueue_session_for_trigger(
        repository=repository,
        kind=trigger_type,
        subject_type=subject_type,
        subject_id=subject_id,
        source=WEBHOOK_AUDIT_SOURCE,
        extra={
            "delivery_id": event.delivery_id,
            "event": event.event,
            "action": event.action,
            **extra,
        },
    )


def _active_installation_for_event(
    event: GitHubWebhookEvent,
) -> GitHubInstallation | None:
    if event.github_installation_id is None:
        return None
    return GitHubInstallation.objects.active().filter(
        github_installation_id=event.github_installation_id
    ).first()


def _active_repository_for_event(event: GitHubWebhookEvent) -> ManagedRepository | None:
    if event.github_installation_id is None or event.github_repository_id is None:
        return None
    return ManagedRepository.objects.active().filter(
        github_repository_id=event.github_repository_id,
        github_installation__github_installation_id=event.github_installation_id,
    ).first()


def _payload_installation_id(payload: dict[str, Any]) -> int | None:
    installation = payload.get("installation")
    if not isinstance(installation, dict) or installation.get("id") in (None, ""):
        return None
    return _payload_positive_int(installation["id"], "installation.id")


def _payload_repository_id(payload: dict[str, Any]) -> int | None:
    repository = payload.get("repository")
    if not isinstance(repository, dict) or repository.get("id") in (None, ""):
        return None
    return _payload_positive_int(repository["id"], "repository.id")


def _payload_repository_full_name(payload: dict[str, Any]) -> str:
    repository = payload.get("repository")
    if not isinstance(repository, dict):
        return ""
    return str(repository.get("full_name") or "")


def _payload_positive_int(value: Any, field_path: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise GitHubWebhookPayloadError(
            f"GitHub webhook payload field {field_path} must be an integer."
        ) from exc
    if parsed <= 0:
        raise GitHubWebhookPayloadError(
            f"GitHub webhook payload field {field_path} must be positive."
        )
    return parsed


def _store_failed_webhook_delivery(
    *,
    delivery_id: str,
    event_name: str,
    payload: dict[str, Any],
    error: str,
) -> GitHubWebhookIngestResult:
    defaults = {
        "event": event_name,
        "action": str(payload.get("action") or ""),
        "payload": payload,
        "status": GitHubWebhookEvent.Status.FAILED,
        "result": {
            "status": GitHubWebhookEvent.Status.FAILED,
            "error": GitHubWebhookPayloadError.code,
        },
        "processed_at": timezone.now(),
        "last_error": error,
    }
    try:
        event, created = GitHubWebhookEvent.objects.get_or_create(
            delivery_id=delivery_id,
            defaults=defaults,
        )
    except IntegrityError:
        event = GitHubWebhookEvent.objects.get(delivery_id=delivery_id)
        created = False
    return GitHubWebhookIngestResult(
        event=event,
        created=created,
        error_code=GitHubWebhookPayloadError.code,
    )


def _payload_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise GitHubInstallationSyncError(f"GitHub webhook payload missing {key}.")
    return values


def _optional_payload_list(
    payload: dict[str, Any],
    key: str,
) -> list[dict[str, Any]] | None:
    values = payload.get(key)
    if values is None:
        return None
    if not isinstance(values, list):
        raise GitHubInstallationSyncError(f"GitHub webhook payload invalid {key}.")
    return values


def _processed_result(**values) -> dict[str, Any]:
    return {"status": GitHubWebhookEvent.Status.PROCESSED, **values}


def _ignored_result(reason: str, **values) -> dict[str, Any]:
    return {
        "status": GitHubWebhookEvent.Status.IGNORED,
        "reason": reason,
        **values,
    }
