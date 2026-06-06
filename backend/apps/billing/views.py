from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.models import CustomerOrganization, Membership
from apps.accounts.serializers import CustomerOrganizationSerializer
from apps.billing.serializers import SubscriptionUpdateSerializer
from apps.billing.services import (
    billing_summary_payload,
    update_subscription,
)
from apps.common.api import api_error_response


CUSTOMER_EDITABLE_FIELDS = {"autonomous_pr_add_on_enabled"}
STAFF_EDITABLE_FIELDS = {
    "autonomous_pr_add_on_enabled",
    "plan_code",
    "base_price_cents",
    "autonomous_pr_add_on_price_cents",
}


@api_view(["GET", "PATCH"])
def organization_billing(request, organization_id):
    organization = _visible_organization(request.user, organization_id)
    if organization is None:
        return api_error_response(
            "not_found",
            "Organization not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if not _can_view_billing(request.user, organization):
        return api_error_response(
            "permission_denied",
            "Owner or admin access is required to view billing inputs.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "PATCH":
        serializer = SubscriptionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        editable_fields = _editable_fields(request.user, organization)
        forbidden_fields = set(serializer.validated_data) - editable_fields
        if forbidden_fields:
            return api_error_response(
                "permission_denied",
                "You do not have permission to update those billing fields.",
                details={"fields": sorted(forbidden_fields)},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        update_subscription(
            organization=organization,
            values=serializer.validated_data,
            actor=request.user,
        )

    payload = billing_summary_payload(organization)
    payload["organization"] = CustomerOrganizationSerializer(organization).data
    payload["permissions"] = {
        "can_edit_add_on": "autonomous_pr_add_on_enabled"
        in _editable_fields(request.user, organization),
        "can_edit_plan_and_prices": _can_edit_plan_and_prices(request.user),
    }
    return Response(payload)


def _visible_organization(user, organization_id):
    if not getattr(user, "is_active", False):
        return None
    queryset = CustomerOrganization.objects.active().filter(id=organization_id)
    if getattr(user, "is_staff", False):
        return queryset.first()
    return (
        queryset.filter(
            memberships__user=user,
            memberships__deactivated_at__isnull=True,
        )
        .distinct()
        .first()
    )


def _can_view_billing(user, organization) -> bool:
    if getattr(user, "is_staff", False):
        return True
    return Membership.objects.active().filter(
        user=user,
        organization=organization,
        role__in=[Membership.Role.OWNER, Membership.Role.ADMIN],
    ).exists()


def _editable_fields(user, organization) -> set[str]:
    if _can_edit_plan_and_prices(user):
        return STAFF_EDITABLE_FIELDS
    if _can_view_billing(user, organization):
        return CUSTOMER_EDITABLE_FIELDS
    return set()


def _can_edit_plan_and_prices(user) -> bool:
    return bool(getattr(user, "is_staff", False))
