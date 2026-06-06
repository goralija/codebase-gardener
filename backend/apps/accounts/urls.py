from django.urls import path

from apps.billing.views import organization_billing
from apps.accounts import views
from apps.repositories.views import organization_repositories

urlpatterns = [
    path("", views.organizations, name="organizations"),
    path(
        "<uuid:organization_id>/billing/",
        organization_billing,
        name="organization-billing",
    ),
    path(
        "<uuid:organization_id>/repositories/",
        organization_repositories,
        name="organization-repositories",
    ),
]
