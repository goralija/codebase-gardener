from rest_framework.test import APIClient


def test_health_endpoint_returns_foundation_status():
    response = APIClient().get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "codebase-gardener-backend",
        "version": "0.1.0",
    }

