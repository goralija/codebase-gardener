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
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import CustomerOrganization, Membership
from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError, GitHubAppClient
from apps.github_app.models import GitHubInstallation
from apps.github_app.state import create_install_state, load_install_state
from apps.repositories.models import ManagedRepository


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


@dataclass(frozen=True)
class InstallationCallbackResult:
    status: str
    user: Any | None = None
    organization: CustomerOrganization | None = None
    repository_count: int = 0


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
        repository_count = _sync_repositories(
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
                "repository_count": repository_count,
            },
        )

    return InstallationCallbackResult(
        status="installed",
        user=user,
        organization=organization,
        repository_count=repository_count,
    )


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
) -> int:
    now = timezone.now()
    granted_ids: set[int] = set()

    for payload in repository_payloads:
        repository = _upsert_repository(
            organization=organization,
            installation=installation,
            payload=payload,
            selected_at=now,
        )
        granted_ids.add(repository.github_repository_id)
        if repository._gardener_was_selected:
            AuditEvent.objects.create(
                actor=actor,
                organization=organization,
                github_installation=installation,
                repository=repository,
                event_type=AuditEvent.EventType.MANAGED_REPOSITORY_SELECTED,
                metadata={
                    "github_repository_id": repository.github_repository_id,
                    "full_name": repository.full_name,
                },
            )

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
            metadata={
                "github_repository_id": repository.github_repository_id,
                "full_name": repository.full_name,
            },
        )

    return len(granted_ids)


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
