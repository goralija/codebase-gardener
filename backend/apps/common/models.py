import uuid

from django.conf import settings
from django.db import models


class UUIDTimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditEvent(UUIDTimestampedModel):
    class EventType(models.TextChoices):
        GITHUB_INSTALLATION_SYNCED = (
            "github_installation_synced",
            "GitHub installation synced",
        )
        MANAGED_REPOSITORY_SELECTED = (
            "managed_repository_selected",
            "Managed repository selected",
        )
        MANAGED_REPOSITORY_UNSELECTED = (
            "managed_repository_unselected",
            "Managed repository unselected",
        )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    organization = models.ForeignKey(
        "accounts.CustomerOrganization",
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    github_installation = models.ForeignKey(
        "github_app.GitHubInstallation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    repository = models.ForeignKey(
        "repositories.ManagedRepository",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    event_type = models.CharField(max_length=64, choices=EventType.choices)
    source = models.CharField(max_length=64, default="github_app_oauth_callback")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["repository", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.event_type
