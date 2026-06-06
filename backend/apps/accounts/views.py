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

    serializer = CustomerOrganizationSerializer(organizations_queryset, many=True)
    return Response({"organizations": serializer.data})
