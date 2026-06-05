from django.urls import path

from apps.analysis.views import first_report


urlpatterns = [
    path("first/", first_report, name="first-report"),
]
