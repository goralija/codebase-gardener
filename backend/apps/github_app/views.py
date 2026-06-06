import hashlib
import hmac
import json
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
from apps.github_app.models import GitHubWebhookEvent
from apps.github_app.services import (
    GitHubAppOnboardingError,
    build_installation_start_url,
    complete_installation_callback,
    ingest_github_webhook_delivery,
)
from apps.github_app.state import load_install_state
from apps.github_app.tasks import process_github_webhook_event


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


@api_view(["POST"])
@permission_classes([AllowAny])
def webhook_delivery(request):
    delivery_id = request.headers.get("X-GitHub-Delivery", "").strip()
    event_name = request.headers.get("X-GitHub-Event", "").strip()
    if not delivery_id or not event_name:
        return api_error_response(
            "missing_github_webhook_header",
            "GitHub webhook delivery and event headers are required.",
            details={
                "delivery_id": bool(delivery_id),
                "event": bool(event_name),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        _verify_webhook_signature(request.body, request.headers.get("X-Hub-Signature-256"))
    except ImproperlyConfigured:
        return api_error_response(
            "server_configuration_error",
            "GitHub webhook secret is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except GitHubWebhookSignatureError:
        return api_error_response(
            "invalid_github_webhook_signature",
            "GitHub webhook signature is invalid.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return api_error_response(
            "invalid_github_webhook_payload",
            "GitHub webhook payload must be valid JSON.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(payload, dict):
        return api_error_response(
            "invalid_github_webhook_payload",
            "GitHub webhook payload must be a JSON object.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    ingest_result = ingest_github_webhook_delivery(
        delivery_id=delivery_id,
        event_name=event_name,
        payload=payload,
    )
    if ingest_result.error_code:
        return api_error_response(
            ingest_result.error_code,
            "GitHub webhook payload is invalid.",
            details={"delivery_id": ingest_result.event.delivery_id},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if ingest_result.created or ingest_result.event.status == GitHubWebhookEvent.Status.RECEIVED:
        if not _enqueue_webhook_event(ingest_result.event):
            return api_error_response(
                "github_webhook_queue_unavailable",
                "GitHub webhook was stored but could not be queued for processing.",
                details={"delivery_id": ingest_result.event.delivery_id},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response_status = "accepted" if ingest_result.created else "requeued"
    else:
        response_status = "duplicate"

    return Response(
        {
            "status": response_status,
            "delivery_id": ingest_result.event.delivery_id,
        },
        status=status.HTTP_202_ACCEPTED,
    )


def _frontend_redirect(**params):
    frontend_base_url = settings.FRONTEND_REDIRECT_BASE_URL.rstrip("/")
    query = urlencode(params)
    return redirect(f"{frontend_base_url}/onboarding/github?{query}")


class GitHubWebhookSignatureError(Exception):
    pass


def _enqueue_webhook_event(event: GitHubWebhookEvent) -> bool:
    event.status = GitHubWebhookEvent.Status.QUEUED
    event.last_error = ""
    event.save(update_fields=["status", "last_error", "updated_at"])
    try:
        process_github_webhook_event.delay(str(event.id))
    except Exception as exc:
        event.status = GitHubWebhookEvent.Status.RECEIVED
        event.last_error = f"Webhook queue enqueue failed: {exc.__class__.__name__}"
        event.save(update_fields=["status", "last_error", "updated_at"])
        return False
    return True


def _verify_webhook_signature(payload_body: bytes, signature_header: str | None) -> None:
    secret = settings.GITHUB_WEBHOOK_SECRET.strip()
    if not secret:
        raise ImproperlyConfigured("GITHUB_WEBHOOK_SECRET is required.")
    if not signature_header:
        raise GitHubWebhookSignatureError

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise GitHubWebhookSignatureError
