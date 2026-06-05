import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import CustomerOrganization, Membership
from apps.github_app.models import GitHubInstallation
from apps.repositories.models import ManagedRepository


@pytest.mark.django_db
def test_custom_user_creation_normalizes_email_and_stores_github_identity():
    user = get_user_model().objects.create_user(
        email="Founder@Example.COM",
        password="secret",
        github_user_id=12345,
        github_login="founder",
        github_avatar_url="https://avatars.githubusercontent.com/u/12345",
    )

    assert isinstance(user.id, uuid.UUID)
    assert user.email == "founder@example.com"
    assert user.check_password("secret")
    assert user.github_user_id == 12345
    assert user.github_login == "founder"
    assert user.github_avatar_url == "https://avatars.githubusercontent.com/u/12345"


@pytest.mark.django_db
def test_customer_organization_maps_to_github_org_or_personal_account():
    organization = CustomerOrganization.objects.create(
        name="Acme Engineering",
        github_account_id=1001,
        github_login="acme",
        github_account_type=CustomerOrganization.GitHubAccountType.ORGANIZATION,
    )
    personal_account = CustomerOrganization.objects.create(
        name="Founder",
        github_account_id=1002,
        github_login="founder",
        github_account_type=CustomerOrganization.GitHubAccountType.USER,
    )

    assert organization.is_active
    assert personal_account.is_active
    assert set(CustomerOrganization.objects.active()) == {organization, personal_account}

    personal_account.deactivated_at = timezone.now()
    personal_account.save(update_fields=["deactivated_at", "updated_at"])

    assert set(CustomerOrganization.objects.active()) == {organization}


@pytest.mark.django_db
def test_membership_has_one_active_role_per_user_and_organization():
    user = create_user("maintainer@example.com")
    organization = create_organization(1)

    membership = Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.MAINTAINER,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Membership.objects.create(
                user=user,
                organization=organization,
                role=Membership.Role.VIEWER,
            )

    membership.deactivated_at = timezone.now()
    membership.save(update_fields=["deactivated_at", "updated_at"])
    replacement = Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.ADMIN,
    )

    assert not membership.is_active
    assert replacement.is_active
    assert replacement.role == Membership.Role.ADMIN


@pytest.mark.django_db
def test_installation_and_repository_relationships_do_not_store_tokens():
    organization = create_organization(1)
    installation = create_installation(organization, 1)
    repository = create_repository(organization, installation, 1)

    assert installation.organization == organization
    assert installation.permissions == {"metadata": "read", "contents": "read"}
    assert installation.events == ["installation", "repository"]
    assert not hasattr(installation, "access_token")
    assert repository.organization == organization
    assert repository.github_installation == installation
    assert list(installation.managed_repositories.all()) == [repository]
    assert repository.is_active


@pytest.mark.django_db
def test_installation_rejects_mismatched_customer_organization_account():
    organization = create_organization(1)

    with pytest.raises(ValidationError) as exc_info:
        GitHubInstallation.objects.create(
            organization=organization,
            github_installation_id=2998,
            github_account_id=9998,
            github_account_login=organization.github_login,
            github_account_type=GitHubInstallation.GitHubAccountType.ORGANIZATION,
            repository_selection=GitHubInstallation.RepositorySelection.SELECTED,
        )

    assert "github_account_id" in exc_info.value.message_dict

    with pytest.raises(ValidationError) as exc_info:
        GitHubInstallation.objects.create(
            organization=organization,
            github_installation_id=2999,
            github_account_id=organization.github_account_id,
            github_account_login=organization.github_login,
            github_account_type=GitHubInstallation.GitHubAccountType.USER,
            repository_selection=GitHubInstallation.RepositorySelection.SELECTED,
        )

    assert "github_account_type" in exc_info.value.message_dict


@pytest.mark.django_db
def test_repository_rejects_installation_from_another_organization():
    organization = create_organization(1)
    other_organization = create_organization(2)
    other_installation = create_installation(other_organization, 2)

    with pytest.raises(ValidationError) as exc_info:
        create_repository(organization, other_installation, 7)

    assert "github_installation" in exc_info.value.message_dict


@pytest.mark.django_db
def test_repository_visibility_scopes_to_active_org_members_and_installations():
    user = create_user("viewer@example.com")
    organization = create_organization(1)
    Membership.objects.create(user=user, organization=organization, role=Membership.Role.VIEWER)
    active_installation = create_installation(organization, 1)
    visible_repository = create_repository(organization, active_installation, 1)

    other_organization = create_organization(2)
    other_installation = create_installation(other_organization, 2)
    create_repository(other_organization, other_installation, 2)

    inactive_membership_org = create_organization(3)
    Membership.objects.create(
        user=user,
        organization=inactive_membership_org,
        role=Membership.Role.VIEWER,
        deactivated_at=timezone.now(),
    )
    inactive_membership_installation = create_installation(inactive_membership_org, 3)
    create_repository(inactive_membership_org, inactive_membership_installation, 3)

    suspended_installation = create_installation(organization, 4, suspended_at=timezone.now())
    create_repository(organization, suspended_installation, 4)

    deleted_installation = create_installation(organization, 5, deleted_at=timezone.now())
    create_repository(organization, deleted_installation, 5)

    unselected_repository = create_repository(
        organization,
        active_installation,
        6,
        unselected_at=timezone.now(),
    )

    assert set(ManagedRepository.objects.visible_to(user)) == {visible_repository}
    assert unselected_repository not in ManagedRepository.objects.active()
    assert not ManagedRepository.objects.visible_to(AnonymousUser()).exists()


def create_user(email: str):
    return get_user_model().objects.create_user(email=email, password="secret")


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
    *,
    suspended_at=None,
    deleted_at=None,
) -> GitHubInstallation:
    return GitHubInstallation.objects.create(
        organization=organization,
        github_installation_id=2000 + identifier,
        github_account_id=organization.github_account_id,
        github_account_login=organization.github_login,
        github_account_type=GitHubInstallation.GitHubAccountType.ORGANIZATION,
        repository_selection=GitHubInstallation.RepositorySelection.SELECTED,
        permissions={"metadata": "read", "contents": "read"},
        events=["installation", "repository"],
        suspended_at=suspended_at,
        deleted_at=deleted_at,
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
