import json
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analysis.fixtures import validate_first_report_fixture_contract
from apps.analysis.models import RepositoryAnalysis
from apps.analysis.serializers import FirstReportFixtureSerializer
from tests.test_product_models import (
    create_installation,
    create_organization,
    create_repository,
)


def load_first_report_fixture():
    repo_root = Path(__file__).resolve().parents[2]
    fixture_path = repo_root / "fixtures" / "contracts" / "first_report_fixture.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.mark.django_db
def test_first_report_endpoint_returns_fixture_contract():
    response = APIClient().get("/api/v1/reports/first/")

    assert response.status_code == 200
    assert response.json() == load_first_report_fixture()


@pytest.mark.django_db
@override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5174"])
def test_first_report_endpoint_allows_configured_frontend_origin():
    response = APIClient().get(
        "/api/v1/reports/first/",
        HTTP_ORIGIN="http://localhost:5174",
    )

    assert response.status_code == 200
    assert response["access-control-allow-origin"] == "http://localhost:5174"
    assert response["access-control-allow-credentials"] == "true"


def test_first_report_serializer_requires_top_level_contract_fields():
    payload = load_first_report_fixture()
    payload.pop("entropy_report")

    serializer = FirstReportFixtureSerializer(data=payload)

    assert not serializer.is_valid()
    assert "entropy_report" in serializer.errors


def test_first_report_fixture_contract_validation_rejects_nested_drift():
    payload = load_first_report_fixture()
    payload["entropy_report"].pop("score")

    with pytest.raises(ImproperlyConfigured):
        validate_first_report_fixture_contract(payload)


def test_first_report_fixture_contract_rejects_protected_module_drift():
    payload = load_first_report_fixture()
    payload["repository_constitution"]["protected_modules"][0].pop("paths")

    with pytest.raises(ImproperlyConfigured):
        validate_first_report_fixture_contract(payload)


def test_first_report_fixture_contract_rejects_entropy_component_drift():
    payload = load_first_report_fixture()
    payload["entropy_report"]["score"]["components"].pop("testing")

    with pytest.raises(ImproperlyConfigured):
        validate_first_report_fixture_contract(payload)


def test_first_report_fixture_contract_rejects_phase_result_drift():
    payload = load_first_report_fixture()
    payload["gardening_session_result"]["phase_results"][0].pop("summary")

    with pytest.raises(ImproperlyConfigured):
        validate_first_report_fixture_contract(payload)


def test_first_report_fixture_contract_rejects_pr_body_section_drift():
    payload = load_first_report_fixture()
    payload["maintenance_pr_plans"][0]["pr_body_sections"].pop("verification")

    with pytest.raises(ImproperlyConfigured):
        validate_first_report_fixture_contract(payload)


@pytest.mark.django_db
def test_first_report_endpoint_treats_invalid_fixture_as_server_error(monkeypatch):
    def load_invalid_fixture():
        raise ImproperlyConfigured("bad fixture")

    monkeypatch.setattr("apps.analysis.views.load_first_report_fixture", load_invalid_fixture)

    response = APIClient().get("/api/v1/reports/first/")

    assert response.status_code == 500
    assert response.json() == {
        "code": "server_configuration_error",
        "message": "First report fixture is not available.",
        "details": {},
    }


@pytest.mark.django_db
def test_repository_baseline_report_returns_latest_promoted_baseline(monkeypatch):
    organization = create_organization(1)
    installation = create_installation(organization, 1)
    repository = create_repository(organization, installation, 1)
    older_baseline = RepositoryAnalysis.objects.create(
        organization=organization,
        repository=repository,
        commit_sha="base111",
        source=RepositoryAnalysis.Source.FIRST_SCAN,
        baseline_promoted_at=timezone.now(),
    )
    unpromoted_latest = RepositoryAnalysis.objects.create(
        organization=organization,
        repository=repository,
        commit_sha="latest222",
        source=RepositoryAnalysis.Source.SESSION,
    )
    loaded_analysis_ids = []

    def load_report(analysis):
        loaded_analysis_ids.append(analysis.id)
        payload = load_first_report_fixture()
        payload["analysis_snapshot"]["commit_sha"] = analysis.commit_sha
        return payload

    monkeypatch.setattr("apps.analysis.views.storage_service.load_first_report", load_report)

    response = APIClient().get(f"/api/v1/reports/repository/{repository.id}/baseline/")

    assert response.status_code == 200
    assert response.json()["analysis_snapshot"]["commit_sha"] == "base111"
    assert loaded_analysis_ids == [older_baseline.id]
    assert unpromoted_latest.baseline_promoted_at is None


@pytest.mark.django_db
def test_repository_baseline_report_404_when_no_baseline_promoted():
    organization = create_organization(1)
    installation = create_installation(organization, 1)
    repository = create_repository(organization, installation, 1)
    RepositoryAnalysis.objects.create(
        organization=organization,
        repository=repository,
        commit_sha="latest222",
        source=RepositoryAnalysis.Source.SESSION,
    )

    response = APIClient().get(f"/api/v1/reports/repository/{repository.id}/baseline/")

    assert response.status_code == 404
    assert response.json() == {
        "code": "no_baseline_analysis",
        "message": "No baseline analysis has been promoted for this repository yet.",
        "details": {},
    }
