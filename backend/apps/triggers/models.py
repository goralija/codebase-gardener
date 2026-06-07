from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import UUIDTimestampedModel
from apps.triggers.thresholds import DEFAULT_COMMIT_THRESHOLD


class RepositoryAutomationPolicy(UUIDTimestampedModel):
    class AutonomyMode(models.TextChoices):
        CONSERVATIVE = "conservative", "Conservative"
        ASSISTED = "assisted", "Assisted"
        AUTONOMOUS = "autonomous", "Autonomous"

    organization = models.ForeignKey(
        "accounts.CustomerOrganization",
        on_delete=models.CASCADE,
        related_name="repository_automation_policies",
    )
    repository = models.OneToOneField(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="automation_policy",
    )
    autonomy_mode = models.CharField(
        max_length=32,
        choices=AutonomyMode.choices,
        default=AutonomyMode.CONSERVATIVE,
    )
    manual_trigger_enabled = models.BooleanField(default=True)
    scheduled_trigger_enabled = models.BooleanField(default=False)
    commit_trigger_enabled = models.BooleanField(default=False)
    risky_module_trigger_enabled = models.BooleanField(default=False)
    pr_opened_trigger_enabled = models.BooleanField(default=False)
    ci_failure_trigger_enabled = models.BooleanField(default=False)
    commit_threshold = models.PositiveSmallIntegerField(
        default=DEFAULT_COMMIT_THRESHOLD,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
    )

    class Meta:
        ordering = ["repository__full_name"]
        indexes = [
            models.Index(fields=["organization", "autonomy_mode"]),
        ]

    @classmethod
    def get_or_create_for_repository(cls, repository):
        policy, _created = cls.objects.get_or_create(
            repository=repository,
            defaults={"organization": repository.organization},
        )
        return policy

    def clean(self):
        super().clean()
        if self.repository_id and self.organization_id:
            if self.repository.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        "organization": (
                            "Automation policy organization must match the "
                            "managed repository organization."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        if self.repository_id and not self.organization_id:
            self.organization = self.repository.organization
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.repository} automation policy"


class RepositoryCommitTracker(UUIDTimestampedModel):
    """Accumulates default-branch commits to drive the after-N-commits trigger.

    Incremented on every default-branch push and reset to zero whenever the
    commit-count threshold is crossed and an ``n_commits`` session is enqueued.
    """

    repository = models.OneToOneField(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="commit_tracker",
    )
    commits_since_session = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.repository_id}: {self.commits_since_session} commits"
