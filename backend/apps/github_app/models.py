from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import UUIDTimestampedModel


class GitHubInstallationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(
            suspended_at__isnull=True,
            deleted_at__isnull=True,
            organization__deactivated_at__isnull=True,
        )


class GitHubInstallation(UUIDTimestampedModel):
    class GitHubAccountType(models.TextChoices):
        ORGANIZATION = "organization", "Organization"
        USER = "user", "User"

    class RepositorySelection(models.TextChoices):
        ALL = "all", "All repositories"
        SELECTED = "selected", "Selected repositories"

    organization = models.ForeignKey(
        "accounts.CustomerOrganization",
        on_delete=models.CASCADE,
        related_name="github_installations",
    )
    github_installation_id = models.PositiveBigIntegerField(unique=True)
    github_account_id = models.PositiveBigIntegerField()
    github_account_login = models.CharField(max_length=255)
    github_account_type = models.CharField(max_length=32, choices=GitHubAccountType.choices)
    repository_selection = models.CharField(
        max_length=32,
        choices=RepositorySelection.choices,
        default=RepositorySelection.SELECTED,
    )
    permissions = models.JSONField(default=dict, blank=True)
    events = models.JSONField(default=list, blank=True)
    html_url = models.URLField(blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = GitHubInstallationQuerySet.as_manager()

    class Meta:
        ordering = ["github_account_login", "github_installation_id"]
        indexes = [
            models.Index(fields=["github_account_id"]),
            models.Index(fields=["github_account_login"]),
            models.Index(fields=["suspended_at", "deleted_at"]),
        ]

    @property
    def is_active(self) -> bool:
        return (
            self.suspended_at is None
            and self.deleted_at is None
            and self.organization.deactivated_at is None
        )

    def clean(self):
        super().clean()
        if not self.organization_id:
            return

        errors = {}
        if self.github_account_id != self.organization.github_account_id:
            errors["github_account_id"] = (
                "GitHub installation account must match its customer organization."
            )
        if self.github_account_type != self.organization.github_account_type:
            errors["github_account_type"] = (
                "GitHub installation account type must match its customer organization."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.github_account_login} ({self.github_installation_id})"


class GitHubWebhookEvent(UUIDTimestampedModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    delivery_id = models.CharField(max_length=255, unique=True)
    event = models.CharField(max_length=64)
    action = models.CharField(max_length=64, blank=True)
    github_installation_id = models.PositiveBigIntegerField(null=True, blank=True)
    github_repository_id = models.PositiveBigIntegerField(null=True, blank=True)
    repository_full_name = models.CharField(max_length=512, blank=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.RECEIVED,
    )
    result = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "action"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["github_installation_id"]),
            models.Index(fields=["github_repository_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.event}:{self.delivery_id}"
