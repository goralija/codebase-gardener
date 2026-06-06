from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.models import CustomerOrganization, Membership
from apps.accounts.serializers import CustomerOrganizationSerializer
from apps.common.api import api_error_response
from apps.github_app.models import GitHubInstallation
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
