from collections.abc import Mapping
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def api_error_response(
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    *,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    return Response(
        {
            "code": code,
            "message": message,
            "details": details or {},
        },
        status=status_code,
    )


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    response.data = _error_payload(exc, response.data)
    return response


def _error_payload(exc: Exception, data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and set(data) == {"detail"}:
        return {
            "code": _exception_code(exc, fallback="error"),
            "message": str(data["detail"]),
            "details": {},
        }

    return {
        "code": _exception_code(exc, fallback="validation_error"),
        "message": "Invalid request.",
        "details": _error_details(data),
    }


def _error_details(data: Any) -> Mapping[str, Any]:
    if data is None:
        return {}
    if isinstance(data, Mapping):
        return data
    return {"errors": data}


def _exception_code(exc: Exception, *, fallback: str) -> str:
    get_codes = getattr(exc, "get_codes", None)
    if not callable(get_codes):
        return fallback

    codes = get_codes()
    if isinstance(codes, str):
        return codes

    return fallback
