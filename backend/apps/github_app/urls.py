from django.urls import path

from apps.github_app import views

urlpatterns = [
    path(
        "installations/start/",
        views.installation_start,
        name="github-app-installation-start",
    ),
    path(
        "oauth/callback/",
        views.oauth_callback,
        name="github-app-oauth-callback",
    ),
]
