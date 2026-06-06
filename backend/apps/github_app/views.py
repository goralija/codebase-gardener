from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import redirect
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.common.api import api_error_response
from apps.github_app.services import (
    GitHubAppOnboardingError,
    build_installation_start_url,
    complete_installation_callback,
)
from apps.github_app.state import load_install_state


@api_view(["GET"])
@permission_classes([AllowAny])
def installation_start(_request):
    try:
        install_url = build_installation_start_url(_request.session)
    except ImproperlyConfigured:
        return api_error_response(
            "server_configuration_error",
            "GitHub App installation is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({"install_url": install_url})


@api_view(["GET"])
@permission_classes([AllowAny])
def oauth_callback(request):
    try:
        result = complete_installation_callback(
            code=request.query_params.get("code"),
            state=request.query_params.get("state"),
            installation_id=request.query_params.get("installation_id"),
            setup_action=request.query_params.get("setup_action"),
            state_loader=lambda state: load_install_state(
                state,
                session=request.session,
                consume=True,
            ),
        )
    except GitHubAppOnboardingError as exc:
        return _frontend_redirect(status="error", error=exc.code)

    if result.status == "pending":
        return _frontend_redirect(status="pending")

    login(
        request,
        result.user,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    return _frontend_redirect(
        status="installed",
        organization_id=str(result.organization.id),
    )


def _frontend_redirect(**params):
    frontend_base_url = settings.FRONTEND_REDIRECT_BASE_URL.rstrip("/")
    query = urlencode(params)
    return redirect(f"{frontend_base_url}/onboarding/github?{query}")
