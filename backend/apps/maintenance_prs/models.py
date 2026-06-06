from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import UUIDTimestampedModel


class MaintenancePRPlanQuerySet(models.QuerySet):
    def for_session(self, gardening_session_id: str):
        return self.filter(gardening_session_id=gardening_session_id)


class MaintenancePRPlan(UUIDTimestampedModel):
    repository = models.ForeignKey(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="maintenance_pr_plans",
    )
    gardening_session_id = models.CharField(max_length=255, db_index=True)
    branch_name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    risk_tier = models.CharField(max_length=64, db_index=True)
    confidence = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    changed_paths = models.JSONField(default=list, blank=True)
    pr_body_sections = models.JSONField(default=dict, blank=True)
    required_checks = models.JSONField(default=list, blank=True)
    blocked = models.BooleanField(default=False, db_index=True)
    block_reason = models.TextField(null=True, blank=True)

    objects = MaintenancePRPlanQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["repository", "gardening_session_id"]),
            models.Index(fields=["repository", "blocked"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "gardening_session_id", "branch_name"],
                name="unique_pr_plan_branch_per_repo_session",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.blocked and not self.block_reason:
            errors["block_reason"] = "Blocked plans must include a block reason."
        if not self.blocked and self.block_reason:
            errors["block_reason"] = "Unblocked plans must not include a block reason."
        if not isinstance(self.changed_paths, list):
            errors["changed_paths"] = "Changed paths must be a list."
        if not isinstance(self.required_checks, list):
            errors["required_checks"] = "Required checks must be a list."
        if not isinstance(self.pr_body_sections, dict):
            errors["pr_body_sections"] = "PR body sections must be an object."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def to_contract(self) -> dict:
        return {
            "schema_version": "1.0",
            "maintenance_pr_plan_id": str(self.id),
            "repository_id": str(self.repository_id),
            "gardening_session_id": self.gardening_session_id,
            "maintenance_opportunity_ids": list(
                self.opportunity_links.order_by("created_at", "id").values_list(
                    "maintenance_opportunity_id",
                    flat=True,
                )
            ),
            "branch_name": self.branch_name,
            "title": self.title,
            "risk_tier": self.risk_tier,
            "confidence": self.confidence,
            "changed_paths": self.changed_paths,
            "pr_body_sections": self.pr_body_sections,
            "required_checks": self.required_checks,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }

    def __str__(self) -> str:
        return f"{self.gardening_session_id}: {self.title}"


class MaintenancePRPlanOpportunity(UUIDTimestampedModel):
    plan = models.ForeignKey(
        MaintenancePRPlan,
        on_delete=models.CASCADE,
        related_name="opportunity_links",
    )
    repository = models.ForeignKey(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="maintenance_pr_plan_opportunities",
    )
    gardening_session_id = models.CharField(max_length=255, db_index=True)
    maintenance_opportunity_id = models.CharField(max_length=255)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "maintenance_opportunity_id"],
                name="unique_opportunity_per_pr_plan",
            ),
            models.UniqueConstraint(
                fields=["repository", "gardening_session_id", "maintenance_opportunity_id"],
                name="unique_pr_plan_opportunity_per_repo_session",
            ),
        ]
        indexes = [
            models.Index(fields=["repository", "gardening_session_id"]),
            models.Index(fields=["maintenance_opportunity_id"]),
        ]

    def clean(self):
        super().clean()
        if not self.plan_id:
            return
        if self.repository_id and self.repository_id != self.plan.repository_id:
            raise ValidationError({"repository": "Opportunity link repository must match plan."})
        if self.gardening_session_id and self.gardening_session_id != self.plan.gardening_session_id:
            raise ValidationError(
                {"gardening_session_id": "Opportunity link session must match plan."}
            )

    def save(self, *args, **kwargs):
        if self.plan_id:
            self.repository = self.plan.repository
            self.gardening_session_id = self.plan.gardening_session_id
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.maintenance_opportunity_id
