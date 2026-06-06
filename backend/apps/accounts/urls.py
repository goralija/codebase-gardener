from django.urls import path

from apps.accounts import views
from apps.repositories.views import organization_repositories

urlpatterns = [
    path("", views.organizations, name="organizations"),
    path(
        "<uuid:organization_id>/repositories/",
        organization_repositories,
        name="organization-repositories",
    ),
]
