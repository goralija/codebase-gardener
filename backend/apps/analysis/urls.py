from django.urls import path

from apps.analysis.views import (
    first_report,
    repository_baseline_report,
    repository_report,
)


urlpatterns = [
    path("first/", first_report, name="first-report"),
    path(
        "repository/<uuid:repository_id>/",
        repository_report,
        name="repository-report",
    ),
    path(
        "repository/<uuid:repository_id>/baseline/",
        repository_baseline_report,
        name="repository-baseline-report",
    ),
]
