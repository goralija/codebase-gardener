from django.db import models

from apps.common.models import UUIDTimestampedModel


class GardeningSession(UUIDTimestampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    repository = models.ForeignKey(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="gardening_sessions",
    )
    trigger = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    task_id = models.CharField(max_length=255, blank=True)
    baseline_analysis = models.ForeignKey(
        "analysis.RepositoryAnalysis",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="baseline_gardening_sessions",
    )
    current_analysis = models.ForeignKey(
        "analysis.RepositoryAnalysis",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_gardening_sessions",
    )
    post_pr_refresh_analysis = models.ForeignKey(
        "analysis.RepositoryAnalysis",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="post_pr_refresh_gardening_sessions",
    )
    drift_report = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["repository", "status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["repository", "current_analysis"]),
        ]

    def __str__(self) -> str:
        return f"{self.repository.full_name} session {self.id}"
