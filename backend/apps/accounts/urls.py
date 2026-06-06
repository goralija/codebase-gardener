from django.urls import path

from apps.billing.views import organization_billing
from apps.accounts import views
from apps.repositories.views import organization_repositories
from apps.triggers.views import repository_automation, repository_automation_trigger

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
    path(
        "<uuid:organization_id>/repositories/<uuid:repository_id>/automation/",
        repository_automation,
        name="repository-automation",
    ),
    path(
        "<uuid:organization_id>/repositories/<uuid:repository_id>/automation/trigger/",
        repository_automation_trigger,
        name="repository-automation-trigger",
    ),
]
