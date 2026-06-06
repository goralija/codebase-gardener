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
        MAINTENANCE_PR_CREATED = (
            "maintenance_pr_created",
            "Maintenance PR created",
        )
        MAINTENANCE_PR_CREATION_FAILED = (
            "maintenance_pr_creation_failed",
            "Maintenance PR creation failed",
        )
        MAINTENANCE_PR_OUTCOME_RECORDED = (
            "maintenance_pr_outcome_recorded",
            "Maintenance PR outcome recorded",
        )
        GARDENER_PROFILE_UPDATED = (
            "gardener_profile_updated",
            "Gardener profile updated",
        )
        GARDENER_PROFILE_PR_PROPOSED = (
            "gardener_profile_pr_proposed",
            "Gardener profile PR proposed",
        )
        GARDENER_PROFILE_PR_FAILED = (
            "gardener_profile_pr_failed",
            "Gardener profile PR failed",
        )
        ANALYSIS_STORED = (
            "analysis_stored",
            "Repository analysis stored",
        )
        SESSION_TRIGGER_ENQUEUED = (
            "session_trigger_enqueued",
            "Session trigger enqueued",
        )
        SESSION_TRIGGER_FAILED = (
            "session_trigger_failed",
            "Session trigger failed",
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
