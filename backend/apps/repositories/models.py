from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.utils import timezone

from apps.common.models import UUIDTimestampedModel


class ManagedRepositoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(
            unselected_at__isnull=True,
            deleted_at__isnull=True,
            organization__deactivated_at__isnull=True,
            github_installation__suspended_at__isnull=True,
            github_installation__deleted_at__isnull=True,
            github_installation__organization_id=F("organization_id"),
        )

    def visible_to(self, user):
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return self.none()

        return (
            self.active()
            .filter(
                organization__memberships__user=user,
                organization__memberships__deactivated_at__isnull=True,
            )
            .distinct()
        )


class ManagedRepository(UUIDTimestampedModel):
    organization = models.ForeignKey(
        "accounts.CustomerOrganization",
        on_delete=models.CASCADE,
        related_name="managed_repositories",
    )
    github_installation = models.ForeignKey(
        "github_app.GitHubInstallation",
        on_delete=models.CASCADE,
        related_name="managed_repositories",
    )
    github_repository_id = models.PositiveBigIntegerField(unique=True)
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=512)
    owner_login = models.CharField(max_length=255)
    private = models.BooleanField(default=True)
    default_branch = models.CharField(max_length=255, blank=True)
    html_url = models.URLField(blank=True)
    selected_at = models.DateTimeField(default=timezone.now)
    unselected_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ManagedRepositoryQuerySet.as_manager()

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["owner_login", "name"]),
            models.Index(fields=["unselected_at", "deleted_at"]),
        ]

    @property
    def is_active(self) -> bool:
        return (
            self.unselected_at is None
            and self.deleted_at is None
            and self.organization.deactivated_at is None
            and self.github_installation.suspended_at is None
            and self.github_installation.deleted_at is None
            and self.github_installation.organization_id == self.organization_id
        )

    def clean(self):
        super().clean()
        if not self.organization_id or not self.github_installation_id:
            return

        if self.github_installation.organization_id != self.organization_id:
            raise ValidationError(
                {
                    "github_installation": (
                        "GitHub installation must belong to the repository organization."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name
