import json
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from rest_framework.test import APIClient

from apps.analysis.fixtures import validate_first_report_fixture_contract
from apps.analysis.serializers import FirstReportFixtureSerializer


def load_first_report_fixture():
    repo_root = Path(__file__).resolve().parents[2]
    fixture_path = repo_root / "fixtures" / "contracts" / "first_report_fixture.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_first_report_endpoint_returns_fixture_contract():
    response = APIClient().get("/api/v1/reports/first/")

    assert response.status_code == 200
    assert response.json() == load_first_report_fixture()


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
