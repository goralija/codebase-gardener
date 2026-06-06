from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.models import UUIDTimestampedModel


class RepositoryComplexity(UUIDTimestampedModel):
    class InputStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partial"
        COMPLETE = "complete", "Complete"

    CALCULATION_VERSION = "complexity.v1.equal_thirds"

    organization = models.ForeignKey(
        "accounts.CustomerOrganization",
        on_delete=models.CASCADE,
        related_name="repository_complexities",
    )
    repository = models.OneToOneField(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="complexity",
    )
    source_analysis = models.ForeignKey(
        "analysis.RepositoryAnalysis",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="complexity_calculations",
    )
    input_status = models.CharField(
        max_length=16,
        choices=InputStatus.choices,
        default=InputStatus.PENDING,
    )
    loc = models.PositiveIntegerField(null=True, blank=True)
    module_count = models.PositiveIntegerField(null=True, blank=True)
    contributor_count = models.PositiveIntegerField(null=True, blank=True)
    loc_score = models.FloatField(default=0.0)
    module_score = models.FloatField(default=0.0)
    contributor_score = models.FloatField(default=0.0)
    weighted_score = models.FloatField(default=0.0)
    multiplier = models.FloatField(default=1.0)
    missing_inputs = models.JSONField(default=list, blank=True)
    calculation_version = models.CharField(
        max_length=64,
        default=CALCULATION_VERSION,
    )
    calculated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["repository__full_name"]
        indexes = [
            models.Index(fields=["organization", "input_status"]),
            models.Index(fields=["calculated_at"]),
        ]

    def clean(self):
        super().clean()
        if self.repository_id and self.organization_id:
            if self.repository.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        "organization": (
                            "Repository complexity organization must match "
                            "the managed repository organization."
                        )
                    }
                )
        if self.source_analysis_id and self.repository_id:
            if self.source_analysis.repository_id != self.repository_id:
                raise ValidationError(
                    {
                        "source_analysis": (
                            "Repository complexity source analysis must belong "
                            "to the managed repository."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.repository} complexity {self.multiplier:.2f}x"


class Subscription(UUIDTimestampedModel):
    PLAN_CODE = "managed_repository_base"
    CURRENCY = "USD"
    DEFAULT_BASE_PRICE_CENTS = 2_000
    DEFAULT_AUTONOMOUS_PR_ADD_ON_PRICE_CENTS = 200

    organization = models.OneToOneField(
        "accounts.CustomerOrganization",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan_code = models.CharField(max_length=64, default=PLAN_CODE)
    currency = models.CharField(max_length=3, default=CURRENCY)
    base_price_cents = models.PositiveIntegerField(default=DEFAULT_BASE_PRICE_CENTS)
    autonomous_pr_add_on_enabled = models.BooleanField(default=False)
    autonomous_pr_add_on_price_cents = models.PositiveIntegerField(
        default=DEFAULT_AUTONOMOUS_PR_ADD_ON_PRICE_CENTS,
    )

    class Meta:
        ordering = ["organization__github_login"]

    def clean(self):
        super().clean()
        errors = {}
        if not self.plan_code.strip():
            errors["plan_code"] = "Plan code must not be blank."
        if self.currency != self.CURRENCY:
            errors["currency"] = "Subscription currency must be USD for v1."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.organization} {self.plan_code}"
