import pytest
from django.contrib.auth import get_user_model
from moto import mock_aws
from rest_framework.test import APIClient

from apps.accounts.models import CustomerOrganization, Membership
from apps.analysis import storage_service
from apps.billing.models import RepositoryComplexity
from apps.billing.services import (
    calculate_complexity,
    calculate_complexity_from_artifacts,
)
from apps.common import storage
from apps.common.models import AuditEvent
from apps.github_app.models import GitHubInstallation
from apps.repositories.models import ManagedRepository


BUCKET = "gardener-analysis"


@pytest.fixture(autouse=True)
def _storage_settings(settings):
    settings.OBJECT_STORAGE_ENDPOINT_URL = None
    settings.OBJECT_STORAGE_ACCESS_KEY = "local"
    settings.OBJECT_STORAGE_SECRET_KEY = "localpass123"
    settings.OBJECT_STORAGE_BUCKET = BUCKET
    settings.OBJECT_STORAGE_REGION = "us-east-1"
    storage.reset_client_cache()
    yield
    storage.reset_client_cache()


def test_complexity_formula_uses_equal_thirds_and_caps_range():
    small = calculate_complexity(loc=25_000, module_count=3, contributor_count=5)
    mixed = calculate_complexity(loc=120_000, module_count=9, contributor_count=6)
    large = calculate_complexity(loc=250_001, module_count=21, contributor_count=51)

    assert small.input_status == "complete"
    assert small.weighted_score == 0.0
    assert small.multiplier == 1.0

    assert mixed.loc_score == 0.66
    assert mixed.module_score == 0.66
    assert mixed.contributor_score == 0.33
    assert mixed.weighted_score == 0.55
    assert mixed.multiplier == 2.1

    assert large.weighted_score == 1.0
    assert large.multiplier == 3.0


def test_complexity_formula_keeps_missing_inputs_neutral():
    pending = calculate_complexity(loc=None, module_count=None, contributor_count=None)
    partial = calculate_complexity(loc=42_000, module_count=4, contributor_count=None)

    assert pending.input_status == "pending"
    assert pending.missing_inputs == ["loc", "module_count", "contributor_count"]
    assert pending.multiplier == 1.0

    assert partial.input_status == "partial"
    assert partial.loc_score == 0.33
    assert partial.module_score == 0.33
    assert partial.missing_inputs == ["contributor_count"]
    assert partial.weighted_score == 0.0
    assert partial.multiplier == 1.0


def test_complexity_inputs_extract_from_analysis_artifacts():
    calculation = calculate_complexity_from_artifacts(
        {
            "health": {
                "metrics": [
                    {"nloc": 60_000},
                    {"nloc": 65_000},
                ],
                "repository_metrics": {
                    "modules": [{"name": f"module_{index}"} for index in range(9)],
                    "contributors_json": (
                        '[{"email": "a@example.com"}, {"email": "b@example.com"}, '
                        '{"email": "c@example.com"}]'
                    ),
                },
            },
        }
    )

    assert calculation.input_status == "complete"
    assert calculation.loc == 125_000
    assert calculation.module_count == 9
    assert calculation.contributor_count == 3


def test_complexity_ignores_ranked_scopes_and_author_samples():
    calculation = calculate_complexity_from_artifacts(
        {
            "health": {"metrics": [{"nloc": 12_000, "top_authors": _authors(2)}]},
            "entropy": {
                "scopes": [
                    {"scope_type": "module", "scope_id": f"module_{index}"}
                    for index in range(9)
                ]
            },
            "snapshot": {
                "logical_systems": [
                    {"logical_system_id": "sys_api"},
                    {"logical_system_id": "sys_web"},
                ]
            },
        }
    )

    assert calculation.input_status == "partial"
    assert calculation.module_count is None
    assert calculation.contributor_count is None
    assert calculation.multiplier == 1.0


@pytest.mark.django_db
@mock_aws
def test_store_analysis_refreshes_repository_complexity():
    organization = create_organization(1)
    repository = create_repository(organization, create_installation(organization, 1), 1)

    analysis = storage_service.store_analysis(
        organization=organization,
        repository=repository,
        commit_sha="abc123",
        artifacts=analysis_artifacts(),
    )

    complexity = RepositoryComplexity.objects.get(repository=repository)
    assert complexity.organization == organization
    assert complexity.source_analysis == analysis
    assert complexity.input_status == RepositoryComplexity.InputStatus.COMPLETE
    assert complexity.loc == 120_000
    assert complexity.module_count == 9
    assert complexity.contributor_count == 6
    assert complexity.weighted_score == 0.55
    assert complexity.multiplier == 2.1
    audit = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.REPOSITORY_COMPLEXITY_UPDATED
    )
    assert audit.repository == repository
    assert audit.metadata["previous"] is None
    assert audit.metadata["current"]["multiplier"] == 2.1


@pytest.mark.django_db
def test_repository_api_returns_visible_complexity_only():
    user = get_user_model().objects.create_user("member@example.com", password="secret")
    viewer = get_user_model().objects.create_user("viewer@example.com", password="secret")
    organization = create_organization(1)
    Membership.objects.create(user=user, organization=organization, role=Membership.Role.OWNER)
    Membership.objects.create(user=viewer, organization=organization, role=Membership.Role.VIEWER)
    installation = create_installation(organization, 1)
    visible_repository = create_repository(organization, installation, 1)

    hidden_organization = create_organization(2)
    hidden_installation = create_installation(hidden_organization, 2)
    hidden_repository = create_repository(hidden_organization, hidden_installation, 2)
    create_complexity(hidden_organization, hidden_repository, multiplier=3.0)
    create_complexity(organization, visible_repository, multiplier=2.1)

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(f"/api/v1/organizations/{organization.id}/repositories/")

    assert response.status_code == 200
    repositories = response.json()["repositories"]
    assert [repository["full_name"] for repository in repositories] == [
        visible_repository.full_name
    ]
    assert repositories[0]["complexity"]["multiplier"] == 2.1
    assert repositories[0]["complexity"]["input_status"] == "complete"

    client.force_authenticate(user=viewer)
    viewer_response = client.get(f"/api/v1/organizations/{organization.id}/repositories/")

    assert viewer_response.status_code == 200
    viewer_complexity = viewer_response.json()["repositories"][0]["complexity"]
    assert viewer_complexity["input_status"] == "restricted"
    assert viewer_complexity["multiplier"] == 1.0
    assert viewer_complexity["loc"] is None


def analysis_artifacts():
    return {
        "constitution": {"completeness_score": 0.75},
        "entropy": {
            "score": {"overall": 42.0},
            "scopes": [
                {"scope_type": "module", "scope_id": f"module_{index}"}
                for index in range(9)
            ],
        },
        "opportunities": [],
        "snapshot": {"commit_sha": "abc123", "signals": {}},
        "health": {
            "metrics": [{"nloc": 120_000, "top_authors": _authors(6)}],
            "repository_metrics": {
                "module_count": 9,
                "contributor_count": 6,
            },
        },
        "knowledge_graph": {"nodes": []},
        "dead_code": [],
    }


def _authors(count: int):
    return [{"email": f"contributor-{index}@example.com"} for index in range(count)]


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
