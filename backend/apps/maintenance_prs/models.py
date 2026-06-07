from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.common.models import UUIDTimestampedModel
from apps.maintenance_prs.policy import DEFAULT_CONFIDENCE_THRESHOLD, STALE_RUNNING_TIMEOUT
from apps.triggers.models import RepositoryAutomationPolicy


class MaintenancePRPlanQuerySet(models.QuerySet):
    def for_session(self, gardening_session_id: str):
        return self.filter(gardening_session_id=gardening_session_id)

    def executable(self):
        stale_running_cutoff = timezone.now() - STALE_RUNNING_TIMEOUT
        return self.filter(
            blocked=False,
            approval_status=MaintenancePRPlan.ApprovalStatus.APPROVED,
            risk_tier="tier_1_autonomous",
            confidence__gte=F("confidence_threshold"),
            repository__unselected_at__isnull=True,
            repository__deleted_at__isnull=True,
            repository__organization__deactivated_at__isnull=True,
            repository__github_installation__suspended_at__isnull=True,
            repository__github_installation__deleted_at__isnull=True,
            repository__github_installation__organization_id=F("repository__organization_id"),
        ).filter(
            Q(repository__automation_policy__isnull=True)
            | Q(
                repository__automation_policy__autonomy_mode=(
                    RepositoryAutomationPolicy.AutonomyMode.AUTONOMOUS
                )
            )
        ).filter(
            Q(
                execution_status__in=[
                    MaintenancePRPlan.ExecutionStatus.PENDING,
                    MaintenancePRPlan.ExecutionStatus.FAILED,
                ]
            )
            | Q(
                execution_status=MaintenancePRPlan.ExecutionStatus.RUNNING,
                updated_at__lt=stale_running_cutoff,
            )
        )


class MaintenancePRPlan(UUIDTimestampedModel):
    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class ExecutionStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class TerminalOutcome(models.TextChoices):
        MERGED = "merged", "Merged"
        CLOSED = "closed", "Closed"
        REVERTED = "reverted", "Reverted"

    repository = models.ForeignKey(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="maintenance_pr_plans",
    )
    gardening_session_id = models.CharField(max_length=255, db_index=True)
    branch_name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=64, blank=True, db_index=True)
    risk_tier = models.CharField(max_length=64, db_index=True)
    confidence = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    confidence_threshold = models.FloatField(
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    changed_paths = models.JSONField(default=list, blank=True)
    pr_body_sections = models.JSONField(default=dict, blank=True)
    required_checks = models.JSONField(default=list, blank=True)
    blocked = models.BooleanField(default=False, db_index=True)
    block_reason = models.TextField(null=True, blank=True)
    approval_status = models.CharField(
        max_length=16,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
    )
    execution_status = models.CharField(
        max_length=16,
        choices=ExecutionStatus.choices,
        default=ExecutionStatus.PENDING,
        db_index=True,
    )
    created_pr_number = models.PositiveIntegerField(null=True, blank=True)
    created_pr_url = models.URLField(blank=True)
    created_branch_ref = models.CharField(max_length=255, blank=True)
    merge_commit_sha = models.CharField(max_length=64, blank=True, db_index=True)
    terminal_outcome = models.CharField(
        max_length=32,
        choices=TerminalOutcome.choices,
        blank=True,
        db_index=True,
    )
    terminal_outcome_at = models.DateTimeField(null=True, blank=True)
    outcome_history = models.JSONField(default=list, blank=True)
    execution_error = models.TextField(blank=True)

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
        if not isinstance(self.outcome_history, list):
            errors["outcome_history"] = "Outcome history must be a list."
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
            "confidence_threshold": self.confidence_threshold,
            "changed_paths": self.changed_paths,
            "pr_body_sections": self.pr_body_sections,
            "required_checks": self.required_checks,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "terminal_outcome": self.terminal_outcome or None,
            "terminal_outcome_at": self.terminal_outcome_at.isoformat().replace("+00:00", "Z")
            if self.terminal_outcome_at
            else None,
        }

    def to_execution_status(self) -> dict:
        return {
            "maintenance_pr_plan_id": str(self.id),
            "approval_status": self.approval_status,
            "execution_status": self.execution_status,
            "created_pr_number": self.created_pr_number,
            "created_pr_url": self.created_pr_url or None,
            "created_branch_ref": self.created_branch_ref or None,
            "terminal_outcome": self.terminal_outcome or None,
            "terminal_outcome_at": self.terminal_outcome_at.isoformat().replace("+00:00", "Z")
            if self.terminal_outcome_at
            else None,
            "execution_error": self.execution_error or None,
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
