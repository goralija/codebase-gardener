from django.urls import path

from apps.analysis.views import first_report, repository_report


urlpatterns = [
    path("first/", first_report, name="first-report"),
    path(
        "repository/<uuid:repository_id>/",
        repository_report,
        name="repository-report",
    ),
]
