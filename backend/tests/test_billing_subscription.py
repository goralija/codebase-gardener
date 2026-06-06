import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import CustomerOrganization, Membership
from apps.billing.models import RepositoryComplexity, Subscription
from apps.billing.services import billing_summary_payload
from apps.common.models import AuditEvent
from apps.github_app.models import GitHubInstallation
from apps.repositories.models import ManagedRepository


FRONTEND_ORIGIN = "http://localhost:5173"


@pytest.mark.django_db
def test_billing_summary_uses_active_repositories_and_complexity_units():
    organization = create_organization(1)
    installation = create_installation(organization, 1)
    api_repository = create_repository(organization, installation, 1)
    worker_repository = create_repository(organization, installation, 2)
    create_repository(
        organization,
        installation,
        3,
        unselected_at=timezone.now(),
    )
    create_complexity(organization, api_repository, multiplier=2.1)

    payload = billing_summary_payload(organization)

    assert payload["subscription"]["plan_code"] == "managed_repository_base"
    assert payload["subscription"]["currency"] == "USD"
    assert payload["subscription"]["base_price_cents"] == 2_000
    assert payload["subscription"]["autonomous_pr_add_on_price_cents"] == 200
    assert payload["subscription"]["autonomous_pr_add_on_enabled"] is False
    assert payload["billing"] == {
        "active_managed_repository_count": 2,
        "billable_repository_units": 3.1,
        "base_subtotal_cents": 6_200,
        "autonomous_pr_add_on_subtotal_cents": 0,
        "monthly_estimate_cents": 6_200,
    }
    assert [
        (repository["full_name"], repository["billable_units"], repository["base_monthly_cents"])
        for repository in payload["repositories"]
    ] == [
        (api_repository.full_name, 2.1, 4_200),
        (worker_repository.full_name, 1.0, 2_000),
    ]


@pytest.mark.django_db
def test_owner_can_view_and_toggle_autonomous_pr_add_on():
    owner = get_user_model().objects.create_user("owner@example.com", password="secret")
    organization = create_organization(1)
    Membership.objects.create(user=owner, organization=organization, role=Membership.Role.OWNER)

    client = APIClient()
    client.force_authenticate(user=owner)

    get_response = client.get(f"/api/v1/organizations/{organization.id}/billing/")

    assert get_response.status_code == 200
    assert get_response.json()["permissions"] == {
        "can_edit_add_on": True,
        "can_edit_plan_and_prices": False,
    }

    patch_response = client.patch(
        f"/api/v1/organizations/{organization.id}/billing/",
        {"autonomous_pr_add_on_enabled": True},
        format="json",
    )

    assert patch_response.status_code == 200
    payload = patch_response.json()
    assert payload["subscription"]["autonomous_pr_add_on_enabled"] is True
    assert payload["billing"]["autonomous_pr_add_on_subtotal_cents"] == 200
    assert AuditEvent.objects.get(
        event_type=AuditEvent.EventType.BILLING_SUBSCRIPTION_UPDATED
    ).metadata["changed_fields"] == ["autonomous_pr_add_on_enabled"]


@pytest.mark.django_db
def test_owner_can_toggle_add_on_from_frontend_origin_with_session_csrf():
    owner = get_user_model().objects.create_user("owner@example.com", password="secret")
    organization = create_organization(1)
    Membership.objects.create(user=owner, organization=organization, role=Membership.Role.OWNER)

    client = Client(enforce_csrf_checks=True, HTTP_HOST="localhost")
    client.force_login(owner)
    csrf_response = client.get("/api/v1/github-app/installations/start/")
    csrf_token = csrf_response.cookies["csrftoken"].value

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/billing/",
        '{"autonomous_pr_add_on_enabled": true}',
        content_type="application/json",
        HTTP_ORIGIN=FRONTEND_ORIGIN,
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert response.status_code == 200
    assert response.json()["subscription"]["autonomous_pr_add_on_enabled"] is True


@pytest.mark.django_db
def test_customer_admin_cannot_edit_staff_only_billing_fields():
    admin = get_user_model().objects.create_user("admin@example.com", password="secret")
    organization = create_organization(1)
    Membership.objects.create(user=admin, organization=organization, role=Membership.Role.ADMIN)
    Subscription.objects.create(organization=organization)

    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/billing/",
        {"base_price_cents": 5_000},
        format="json",
    )

    assert response.status_code == 403
    assert response.json()["details"] == {"fields": ["base_price_cents"]}
    subscription = Subscription.objects.get(organization=organization)
    assert subscription.base_price_cents == 2_000


@pytest.mark.django_db
def test_staff_can_edit_plan_and_price_fields_without_membership():
    staff = get_user_model().objects.create_user(
        "staff@example.com",
        password="secret",
        is_staff=True,
    )
    organization = create_organization(1)

    client = APIClient()
    client.force_authenticate(user=staff)

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/billing/",
        {
            "plan_code": "managed_repository_base_v2",
            "base_price_cents": 2_500,
            "autonomous_pr_add_on_price_cents": 500,
            "autonomous_pr_add_on_enabled": False,
        },
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["permissions"] == {
        "can_edit_add_on": True,
        "can_edit_plan_and_prices": True,
    }
    assert payload["subscription"]["plan_code"] == "managed_repository_base_v2"
    assert payload["subscription"]["base_price_cents"] == 2_500
    assert payload["subscription"]["autonomous_pr_add_on_price_cents"] == 500
    assert payload["subscription"]["autonomous_pr_add_on_enabled"] is False


@pytest.mark.django_db
def test_viewer_and_non_member_cannot_view_billing_inputs():
    viewer = get_user_model().objects.create_user("viewer@example.com", password="secret")
    stranger = get_user_model().objects.create_user("stranger@example.com", password="secret")
    organization = create_organization(1)
    Membership.objects.create(
        user=viewer,
        organization=organization,
        role=Membership.Role.VIEWER,
    )

    client = APIClient()
    client.force_authenticate(user=viewer)
    viewer_response = client.get(f"/api/v1/organizations/{organization.id}/billing/")

    assert viewer_response.status_code == 403

    client.force_authenticate(user=stranger)
    stranger_response = client.get(f"/api/v1/organizations/{organization.id}/billing/")

    assert stranger_response.status_code == 404


def create_organization(identifier: int) -> CustomerOrganization:
    return CustomerOrganization.objects.create(
        name=f"Organization {identifier}",
        github_account_id=1000 + identifier,
        github_login=f"org-{identifier}",
        github_account_type=CustomerOrganization.GitHubAccountType.ORGANIZATION,
    )


def create_installation(
    organization: CustomerOrganization,
    identifier: int,
) -> GitHubInstallation:
    return GitHubInstallation.objects.create(
        organization=organization,
        github_installation_id=2000 + identifier,
        github_account_id=organization.github_account_id,
        github_account_login=organization.github_login,
        github_account_type=GitHubInstallation.GitHubAccountType.ORGANIZATION,
        repository_selection=GitHubInstallation.RepositorySelection.SELECTED,
    )


def create_repository(
    organization: CustomerOrganization,
    installation: GitHubInstallation,
    identifier: int,
    *,
    unselected_at=None,
) -> ManagedRepository:
    return ManagedRepository.objects.create(
        organization=organization,
        github_installation=installation,
        github_repository_id=3000 + identifier,
        name=f"repo-{identifier}",
        full_name=f"{organization.github_login}/repo-{identifier}",
        owner_login=organization.github_login,
        private=True,
        default_branch="main",
        html_url=f"https://github.com/{organization.github_login}/repo-{identifier}",
        unselected_at=unselected_at,
    )


def create_complexity(
    organization: CustomerOrganization,
    repository: ManagedRepository,
    *,
    multiplier: float,
) -> RepositoryComplexity:
    return RepositoryComplexity.objects.create(
        organization=organization,
        repository=repository,
        input_status=RepositoryComplexity.InputStatus.COMPLETE,
        loc=120_000,
        module_count=9,
        contributor_count=6,
        loc_score=0.66,
        module_score=0.66,
        contributor_score=0.33,
        weighted_score=0.55,
        multiplier=multiplier,
        missing_inputs=[],
    )
