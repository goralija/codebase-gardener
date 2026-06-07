from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.models import CustomerOrganization
from apps.accounts.serializers import CustomerOrganizationSerializer


@api_view(["GET"])
def organizations(request):
    organizations_queryset = CustomerOrganization.objects.none()
    if request.user.is_active:
        organizations_queryset = (
            CustomerOrganization.objects.active()
            .filter(
                memberships__user=request.user,
                memberships__deactivated_at__isnull=True,
            )
            .distinct()
        )

    # Live-verify each organization's installation against GitHub so an app that
    # was uninstalled (no delivered webhook) stops reporting as installed.
    from apps.github_app.services import verify_organization_installations

    live_organizations = [
        organization
        for organization in organizations_queryset
        if verify_organization_installations(organization)
    ]

    serializer = CustomerOrganizationSerializer(live_organizations, many=True)
    return Response({"organizations": serializer.data})
