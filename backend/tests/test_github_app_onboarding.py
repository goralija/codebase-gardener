from urllib.parse import parse_qs, urlparse

import pytest
import httpx
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import CustomerOrganization, Membership
from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError, GitHubAppClient
from apps.github_app.models import GitHubInstallation
from apps.github_app.services import sync_installation_from_github_payloads
from apps.github_app.state import load_install_state
from apps.repositories.models import ManagedRepository


FRONTEND_BASE_URL = "http://localhost:5173"


@pytest.mark.django_db
@override_settings(GITHUB_APP_SLUG="codebase-gardener", GITHUB_WEB_BASE_URL="https://github.com")
def test_install_start_returns_signed_state_github_install_url():
    client = APIClient()

    response = client.get("/api/v1/github-app/installations/start/")

    assert response.status_code == 200
    install_url = response.json()["install_url"]
    parsed_url = urlparse(install_url)
    query = parse_qs(parsed_url.query)

    assert install_url.startswith("https://github.com/apps/codebase-gardener/installations/new?")
    assert "csrftoken" in response.cookies
    assert (
        load_install_state(query["state"][0], session=client.session)["purpose"]
        == "github_app_install"
    )


@pytest.mark.django_db
@override_settings(FRONTEND_REDIRECT_BASE_URL=FRONTEND_BASE_URL)
def test_oauth_callback_rejects_invalid_state():
    response = APIClient().get(
        "/api/v1/github-app/oauth/callback/",
        {"code": "code", "installation_id": "2001", "state": "bad-state"},
    )

    assert response.status_code == 302
    assert response["Location"] == (
        f"{FRONTEND_BASE_URL}/onboarding/github?"
        "status=error&error=invalid_install_state"
    )
    assert not get_user_model().objects.exists()


@pytest.mark.django_db
@override_settings(FRONTEND_REDIRECT_BASE_URL=FRONTEND_BASE_URL)
def test_oauth_callback_rejects_missing_required_params():
    client = APIClient()
    state = start_install_state(client)

    response = client.get(
        "/api/v1/github-app/oauth/callback/",
        {"state": state},
    )

    assert response.status_code == 302
    assert response["Location"] == (
        f"{FRONTEND_BASE_URL}/onboarding/github?"
        "status=error&error=missing_required_callback_parameter"
    )
    assert not get_user_model().objects.exists()


@pytest.mark.django_db
@override_settings(FRONTEND_REDIRECT_BASE_URL=FRONTEND_BASE_URL)
def test_oauth_callback_handles_pending_install_request_without_sync():
    client = APIClient()
    state = start_install_state(client)

    response = client.get(
        "/api/v1/github-app/oauth/callback/",
        {"state": state, "setup_action": "request"},
    )

    assert response.status_code == 302
    assert response["Location"] == f"{FRONTEND_BASE_URL}/onboarding/github?status=pending"
    assert not get_user_model().objects.exists()
    assert not GitHubInstallation.objects.exists()


@pytest.mark.django_db
@override_settings(FRONTEND_REDIRECT_BASE_URL=FRONTEND_BASE_URL)
def test_oauth_callback_rejects_state_from_another_session():
    install_client = APIClient()
    state = start_install_state(install_client)

    response = APIClient().get(
        "/api/v1/github-app/oauth/callback/",
        {"code": "code", "installation_id": "2001", "state": state},
    )

    assert response.status_code == 302
    assert response["Location"] == (
        f"{FRONTEND_BASE_URL}/onboarding/github?"
        "status=error&error=invalid_install_state"
    )
    assert not get_user_model().objects.exists()
    assert not GitHubInstallation.objects.exists()


@pytest.mark.django_db
@override_settings(FRONTEND_REDIRECT_BASE_URL=FRONTEND_BASE_URL)
def test_oauth_callback_rejects_reused_state():
    client = APIClient()
    state = start_install_state(client)

    first_response = client.get(
        "/api/v1/github-app/oauth/callback/",
        {"state": state, "setup_action": "request"},
    )
    second_response = client.get(
        "/api/v1/github-app/oauth/callback/",
        {"state": state, "setup_action": "request"},
    )

    assert first_response.status_code == 302
    assert first_response["Location"] == (
        f"{FRONTEND_BASE_URL}/onboarding/github?status=pending"
    )
    assert second_response.status_code == 302
    assert second_response["Location"] == (
        f"{FRONTEND_BASE_URL}/onboarding/github?"
        "status=error&error=invalid_install_state"
    )


@pytest.mark.django_db
@override_settings(FRONTEND_REDIRECT_BASE_URL=FRONTEND_BASE_URL)
def test_oauth_callback_rejects_spoofed_installation_id(monkeypatch):
    fake_client = FakeGitHubClient(verification_error=True)
    monkeypatch.setattr("apps.github_app.services.GitHubAppClient", lambda: fake_client)
    client = APIClient()
    state = start_install_state(client)

    response = client.get(
        "/api/v1/github-app/oauth/callback/",
        {
            "code": "code",
            "installation_id": "9999",
            "state": state,
        },
    )

    assert response.status_code == 302
    assert response["Location"] == (
        f"{FRONTEND_BASE_URL}/onboarding/github?"
        "status=error&error=github_installation_verification_failed"
    )
    assert fake_client.verified_installation_id == 9999
    assert not get_user_model().objects.exists()
    assert not GitHubInstallation.objects.exists()


@pytest.mark.django_db
@override_settings(FRONTEND_REDIRECT_BASE_URL=FRONTEND_BASE_URL)
def test_oauth_callback_rejects_non_admin_org_installer(monkeypatch):
    fake_client = FakeGitHubClient(membership_role="member")
    monkeypatch.setattr("apps.github_app.services.GitHubAppClient", lambda: fake_client)
    client = APIClient()
    state = start_install_state(client)

    response = client.get(
        "/api/v1/github-app/oauth/callback/",
        {
            "code": "code",
            "installation_id": "2001",
            "state": state,
        },
    )

    assert response.status_code == 302
    assert response["Location"] == (
        f"{FRONTEND_BASE_URL}/onboarding/github?"
        "status=error&error=github_installer_authorization_failed"
    )
    assert fake_client.membership_check == ("acme", "octo-founder")
    assert not get_user_model().objects.exists()
    assert not GitHubInstallation.objects.exists()


@pytest.mark.django_db
@override_settings(FRONTEND_REDIRECT_BASE_URL=FRONTEND_BASE_URL)
def test_oauth_callback_creates_owner_installation_repositories_and_audit_events(monkeypatch):
    fake_client = FakeGitHubClient()
    monkeypatch.setattr("apps.github_app.services.GitHubAppClient", lambda: fake_client)

    client = APIClient()
    state = start_install_state(client)
    response = client.get(
        "/api/v1/github-app/oauth/callback/",
        {
            "code": "code",
            "installation_id": "2001",
            "state": state,
        },
    )

    organization = CustomerOrganization.objects.get()
    user = get_user_model().objects.get()
    installation = GitHubInstallation.objects.get()
    repositories = ManagedRepository.objects.order_by("full_name")

    assert response.status_code == 302
    assert response["Location"] == (
        f"{FRONTEND_BASE_URL}/onboarding/github?"
        f"status=installed&organization_id={organization.id}"
    )
    assert user.email == "github-501@users.codebase-gardener.local"
    assert user.github_user_id == 501
    assert Membership.objects.get(user=user, organization=organization).role == "owner"
    assert organization.github_login == "acme"
    assert installation.github_installation_id == 2001
    assert installation.html_url == "https://github.com/organizations/acme/settings/installations/2001"
    assert [repository.full_name for repository in repositories] == [
        "acme/api",
        "acme/web",
    ]
    assert all(repository.is_active for repository in repositories)
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.GITHUB_INSTALLATION_SYNCED
    ).count() == 1
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.MANAGED_REPOSITORY_SELECTED
    ).count() == 2
    assert "user-token" not in _persisted_values()
    assert "installation-token" not in _persisted_values()


def test_github_client_retries_retryable_statuses(monkeypatch):
    responses = [
        httpx.Response(429, json={"message": "rate limited"}),
        httpx.Response(200, json={"login": "octo-founder"}),
    ]
    requests = []

    def fake_request(method, url, *, data=None, json=None, headers=None, params=None, timeout=None):
        requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
            }
        )
        return responses.pop(0)

    monkeypatch.setattr("apps.github_app.client.httpx.request", fake_request)
    client = GitHubAppClient(
        api_base_url="https://api.github.test",
        web_base_url="https://github.test",
        retry_backoff_seconds=0,
    )

    assert client.get_authenticated_user("user-token") == {"login": "octo-founder"}
    assert [request["url"] for request in requests] == [
        "https://api.github.test/user",
        "https://api.github.test/user",
    ]


@pytest.mark.django_db
def test_installation_resync_marks_removed_grants_inactive_and_reactivates_regrants():
    sync_installation_from_github_payloads(
        github_user=github_user_payload(),
        installation_payload=installation_payload(),
        repository_payloads=[
            repository_payload(3001, "api"),
            repository_payload(3002, "web"),
        ],
    )

    sync_installation_from_github_payloads(
        github_user=github_user_payload(),
        installation_payload=installation_payload(),
        repository_payloads=[repository_payload(3002, "web")],
    )

    removed_repository = ManagedRepository.objects.get(github_repository_id=3001)
    retained_repository = ManagedRepository.objects.get(github_repository_id=3002)
    assert removed_repository.unselected_at is not None
    assert retained_repository.unselected_at is None

    sync_installation_from_github_payloads(
        github_user=github_user_payload(),
        installation_payload=installation_payload(),
        repository_payloads=[
            repository_payload(3001, "api"),
            repository_payload(3002, "web"),
        ],
    )

    removed_repository.refresh_from_db()
    assert removed_repository.unselected_at is None
    assert ManagedRepository.objects.active().count() == 2
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.MANAGED_REPOSITORY_UNSELECTED
    ).count() == 1
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.MANAGED_REPOSITORY_SELECTED
    ).count() == 3


@pytest.mark.django_db
def test_organization_and_repository_apis_scope_to_active_membership_installation_and_repos():
    user = get_user_model().objects.create_user("member@example.com", password="secret")
    other_user = get_user_model().objects.create_user("other@example.com", password="secret")
    organization = create_organization(1)
    Membership.objects.create(user=user, organization=organization, role=Membership.Role.VIEWER)
    installation = create_installation(organization, 1)
    visible_repository = create_repository(organization, installation, 1)
    create_repository(organization, installation, 2, unselected=True)

    other_organization = create_organization(2)
    Membership.objects.create(
        user=user,
        organization=other_organization,
        role=Membership.Role.VIEWER,
        deactivated_at=timezone.now(),
    )
    other_installation = create_installation(other_organization, 2)
    create_repository(other_organization, other_installation, 3)

    client = APIClient()
    client.force_authenticate(user=user)

    organizations_response = client.get("/api/v1/organizations/")
    repositories_response = client.get(f"/api/v1/organizations/{organization.id}/repositories/")

    assert organizations_response.status_code == 200
    assert organizations_response.json()["organizations"] == [
        {
            "id": str(organization.id),
            "name": organization.name,
            "github_login": organization.github_login,
            "github_account_type": organization.github_account_type,
        }
    ]
    assert repositories_response.status_code == 200
    assert repositories_response.json()["installation"]["html_url"] == installation.html_url
    assert repositories_response.json()["repositories"] == [
        {
            "id": str(visible_repository.id),
            "github_repository_id": visible_repository.github_repository_id,
            "name": visible_repository.name,
            "full_name": visible_repository.full_name,
            "owner_login": visible_repository.owner_login,
            "private": True,
            "default_branch": "main",
            "html_url": visible_repository.html_url,
            "selected_at": visible_repository.selected_at.isoformat().replace("+00:00", "Z"),
            "complexity": restricted_complexity_payload(),
        }
    ]

    client.force_authenticate(user=other_user)
    denied_response = client.get(f"/api/v1/organizations/{organization.id}/repositories/")

    assert denied_response.status_code == 404
    assert denied_response.json()["code"] == "not_found"
    assert APIClient().get("/api/v1/organizations/").status_code == 403


class FakeGitHubClient:
    def __init__(
        self,
        *,
        verification_error: bool = False,
        membership_role: str = "admin",
    ):
        self.verification_error = verification_error
        self.membership_role = membership_role
        self.verified_installation_id = None
        self.membership_check = None

    def exchange_oauth_code(self, code):
        assert code == "code"
        return "user-token"

    def get_authenticated_user(self, user_token):
        assert user_token == "user-token"
        return github_user_payload()

    def list_user_installation_repositories(self, user_token, installation_id):
        assert user_token == "user-token"
        self.verified_installation_id = installation_id
        if self.verification_error:
            raise GitHubAPIError("not found", status_code=404)
        return [repository_payload(3001, "api")]

    def get_installation(self, installation_id):
        assert installation_id == 2001
        return installation_payload()

    def get_organization_membership(self, user_token, *, org_login, username):
        assert user_token == "user-token"
        self.membership_check = (org_login, username)
        return {"state": "active", "role": self.membership_role}

    def create_installation_token(self, installation_id):
        assert installation_id == 2001
        return "installation-token"

    def list_installation_repositories(self, installation_token):
        assert installation_token == "installation-token"
        return [
            repository_payload(3001, "api"),
            repository_payload(3002, "web"),
        ]


def github_user_payload():
    return {
        "id": 501,
        "login": "octo-founder",
        "email": None,
        "avatar_url": "https://avatars.githubusercontent.com/u/501",
    }


def installation_payload():
    return {
        "id": 2001,
        "account": {
            "id": 1001,
            "login": "acme",
            "type": "Organization",
        },
        "repository_selection": "selected",
        "permissions": {"metadata": "read", "contents": "read"},
        "events": ["installation", "repository"],
        "html_url": "https://github.com/organizations/acme/settings/installations/2001",
        "suspended_at": None,
    }


def repository_payload(identifier: int, name: str):
    return {
        "id": identifier,
        "name": name,
        "full_name": f"acme/{name}",
        "owner": {"login": "acme"},
        "private": True,
        "default_branch": "main",
        "html_url": f"https://github.com/acme/{name}",
    }


def restricted_complexity_payload():
    return {
        "input_status": "restricted",
        "loc": None,
        "module_count": None,
        "contributor_count": None,
        "loc_score": 0.0,
        "module_score": 0.0,
        "contributor_score": 0.0,
        "weighted_score": 0.0,
        "multiplier": 1.0,
        "calculation_version": "complexity.v1.equal_thirds",
        "source_analysis_id": None,
        "source_commit_sha": None,
        "missing_inputs": [],
        "calculated_at": None,
    }


def create_organization(identifier: int):
    return CustomerOrganization.objects.create(
        name=f"Organization {identifier}",
        github_account_id=9000 + identifier,
        github_login=f"org-{identifier}",
        github_account_type=CustomerOrganization.GitHubAccountType.ORGANIZATION,
    )


def create_installation(organization, identifier: int):
    return GitHubInstallation.objects.create(
        organization=organization,
        github_installation_id=8000 + identifier,
        github_account_id=organization.github_account_id,
        github_account_login=organization.github_login,
        github_account_type=GitHubInstallation.GitHubAccountType.ORGANIZATION,
        repository_selection=GitHubInstallation.RepositorySelection.SELECTED,
        permissions={"metadata": "read"},
        events=["installation"],
        html_url=f"https://github.com/organizations/{organization.github_login}/settings/installations/{8000 + identifier}",
    )


def create_repository(organization, installation, identifier: int, *, unselected=False):
    return ManagedRepository.objects.create(
        organization=organization,
        github_installation=installation,
        github_repository_id=7000 + identifier,
        name=f"repo-{identifier}",
        full_name=f"{organization.github_login}/repo-{identifier}",
        owner_login=organization.github_login,
        private=True,
        default_branch="main",
        html_url=f"https://github.com/{organization.github_login}/repo-{identifier}",
        unselected_at=timezone.now() if unselected else None,
    )


def start_install_state(client: APIClient) -> str:
    response = client.get("/api/v1/github-app/installations/start/")
    assert response.status_code == 200
    return parse_qs(urlparse(response.json()["install_url"]).query)["state"][0]


def _persisted_values() -> str:
    values = [
        *get_user_model().objects.values_list("email", "github_login", "github_avatar_url"),
        *GitHubInstallation.objects.values_list("permissions", "events", "html_url"),
        *AuditEvent.objects.values_list("metadata", flat=True),
    ]
    return repr(values)
