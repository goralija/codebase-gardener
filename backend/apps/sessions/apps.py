from django.apps import AppConfig


class SessionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "gardener_sessions"
    name = "apps.sessions"
