from django.test import override_settings
from django.urls import path
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIClient

from apps.common.api import api_error_response, api_exception_handler


@api_view(["GET"])
@permission_classes([AllowAny])
def not_found_view(_request):
    raise NotFound("First report not found.")


@api_view(["GET"])
def protected_view(_request):
    return Response({"status": "ok"})


urlpatterns = [
    path("not-found/", not_found_view),
    path("protected/", protected_view),
]


def test_api_error_response_uses_standard_shape():
    response = api_error_response(
        "missing_resource",
        "The requested resource was not found.",
        {"resource": "first_report"},
        status_code=status.HTTP_404_NOT_FOUND,
    )

    assert response.status_code == 404
    assert response.data == {
        "code": "missing_resource",
        "message": "The requested resource was not found.",
        "details": {"resource": "first_report"},
    }


def test_api_exception_handler_wraps_detail_errors():
    response = api_exception_handler(NotFound("First report not found."), {})

    assert response is not None
    assert response.status_code == 404
    assert response.data == {
        "code": "not_found",
        "message": "First report not found.",
        "details": {},
    }


def test_api_exception_handler_wraps_validation_errors():
    response = api_exception_handler(ValidationError({"name": ["This field is required."]}), {})

    assert response is not None
    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert response.data["message"] == "Invalid request."
    assert "name" in response.data["details"]


@override_settings(ROOT_URLCONF=__name__)
def test_api_exception_handler_is_wired_through_drf_settings():
    response = APIClient().get("/not-found/")

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "First report not found.",
        "details": {},
    }


@override_settings(ROOT_URLCONF=__name__)
def test_api_views_require_authentication_by_default():
    response = APIClient().get("/protected/")

    assert response.status_code == 403
    assert response.json()["code"] == "not_authenticated"
