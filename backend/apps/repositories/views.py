from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.models import CustomerOrganization, Membership
from apps.accounts.serializers import CustomerOrganizationSerializer
from apps.common.api import api_error_response
from apps.common import storage
from apps.common.models import AuditEvent
from apps.github_app.models import GitHubInstallation
from apps.github_app.services import (
    GitHubInstallationSyncError,
    refresh_installation_repositories_from_github,
)
from apps.repositories.models import ManagedRepository
from apps.repositories.serializers import (
    GitHubInstallationSummarySerializer,
    ManagedRepositorySerializer,
)


@api_view(["GET"])
def organization_repositories(request, organization_id):
    organization = _visible_organization(request.user, organization_id)
    if organization is None:
        return api_error_response(
            "not_found",
            "Organization not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    installation = (
        GitHubInstallation.objects.active()
        .filter(organization=organization)
        .order_by("-updated_at")
        .first()
    )
    if installation is None:
        return api_error_response(
            "github_installation_not_found",
            "Active GitHub installation not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if _should_refresh_repository_grants(request) and _can_refresh_repository_grants(
        request.user,
        organization,
    ):
        try:
            refresh_installation_repositories_from_github(
                installation=installation,
                actor=request.user,
            )
            installation.refresh_from_db()
        except GitHubInstallationSyncError:
            return api_error_response(
                "github_installation_sync_failed",
                "Could not refresh GitHub repository access.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    repositories = (
        ManagedRepository.objects.visible_to(request.user)
        .select_related("complexity", "complexity__source_analysis")
        .filter(organization=organization, github_installation=installation)
        .order_by("full_name")
    )

    return Response(
        {
            "organization": CustomerOrganizationSerializer(organization).data,
            "installation": GitHubInstallationSummarySerializer(installation).data,
            "repositories": ManagedRepositorySerializer(
                repositories,
                many=True,
                context={
                    "include_complexity_details": _can_view_complexity_details(
                        request.user,
                        organization,
                    )
                },
            ).data,
        }
    )


@api_view(["DELETE"])
def organization_repository(request, organization_id, repository_id):
    organization = _visible_organization(request.user, organization_id)
    if organization is None:
        return api_error_response(
            "not_found",
            "Organization not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    repository = (
        ManagedRepository.objects.visible_to(request.user)
        .select_related("github_installation")
        .filter(id=repository_id, organization=organization)
        .first()
    )
    if repository is None:
        return api_error_response(
            "not_found",
            "Repository not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if not _can_delete_repository(request.user, organization):
        return api_error_response(
            "permission_denied",
            "You do not have permission to remove this repository.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    repository_metadata = {
        "repository_id": str(repository.id),
        "github_repository_id": repository.github_repository_id,
        "full_name": repository.full_name,
        "github_installation_id": repository.github_installation.github_installation_id,
    }
    try:
        deleted_artifact_count = _delete_repository_object_artifacts(repository)
    except (BotoCoreError, ClientError):
        return api_error_response(
            "repository_artifact_delete_failed",
            "Could not remove stored repository artifacts.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    repository_metadata["deleted_artifact_count"] = deleted_artifact_count
    with transaction.atomic():
        AuditEvent.objects.create(
            actor=request.user,
            organization=organization,
            github_installation=repository.github_installation,
            repository=repository,
            event_type=AuditEvent.EventType.MANAGED_REPOSITORY_HARD_DELETED,
            source="dashboard_repository_delete",
            metadata=repository_metadata,
        )
        repository.delete()

    return Response(status=status.HTTP_204_NO_CONTENT)


def _visible_organization(user, organization_id):
    if not getattr(user, "is_active", False):
        return None
    return (
        CustomerOrganization.objects.active()
        .filter(
            id=organization_id,
            memberships__user=user,
            memberships__deactivated_at__isnull=True,
        )
        .distinct()
        .first()
    )


def _can_view_complexity_details(user, organization) -> bool:
    return Membership.objects.active().filter(
        user=user,
        organization=organization,
        role__in=[Membership.Role.OWNER, Membership.Role.ADMIN],
    ).exists()


def _should_refresh_repository_grants(request) -> bool:
    return str(request.query_params.get("refresh") or "").lower() in {"1", "true", "yes"}


def _can_refresh_repository_grants(user, organization) -> bool:
    if not settings.GITHUB_APP_ID.strip() or not settings.GITHUB_APP_PRIVATE_KEY.strip():
        return False
    if getattr(user, "is_staff", False):
        return True
    return Membership.objects.active().filter(
        user=user,
        organization=organization,
        role__in=[
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
            Membership.Role.MAINTAINER,
        ],
    ).exists()


def _can_delete_repository(user, organization) -> bool:
    if getattr(user, "is_staff", False):
        return True
    return Membership.objects.active().filter(
        user=user,
        organization=organization,
        role__in=[
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        ],
    ).exists()


def _delete_repository_object_artifacts(repository) -> int:
    has_blob_refs = repository.analyses.filter(
        Q(snapshot_key__gt="")
        | Q(knowledge_graph_key__gt="")
        | Q(health_key__gt="")
        | Q(dead_code_key__gt="")
    ).exists()
    if not has_blob_refs:
        return 0

    return storage.delete_prefix(
        f"org_{repository.organization_id}/repo_{repository.id}/"
    )
