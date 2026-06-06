from django.db import models

from apps.common.models import UUIDTimestampedModel


class RepositoryAnalysis(UUIDTimestampedModel):
    """A stored analysis run for one repository at one commit.

    Small contracts are kept inline as JSONB for cheap querying; large blobs
    (snapshot, knowledge graph, health, dead-code) live in object storage and
    are referenced here by per-tenant key + checksum. Many rows per repository
    form the history used for trend / diff comparisons.
    """

    organization = models.ForeignKey(
        "accounts.CustomerOrganization",
        on_delete=models.CASCADE,
        related_name="repository_analyses",
    )
    repository = models.ForeignKey(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="analyses",
    )
    commit_sha = models.CharField(max_length=64)

    # Inline small contracts.
    constitution = models.JSONField(default=dict, blank=True)
    entropy = models.JSONField(default=dict, blank=True)
    opportunities = models.JSONField(default=list, blank=True)

    # Object-storage references for large blobs.
    snapshot_key = models.CharField(max_length=512, blank=True)
    snapshot_checksum = models.CharField(max_length=64, blank=True)
    knowledge_graph_key = models.CharField(max_length=512, blank=True)
    knowledge_graph_checksum = models.CharField(max_length=64, blank=True)
    health_key = models.CharField(max_length=512, blank=True)
    health_checksum = models.CharField(max_length=64, blank=True)
    dead_code_key = models.CharField(max_length=512, blank=True)
    dead_code_checksum = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "commit_sha"],
                name="unique_repository_commit_analysis",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "repository", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.repository_id}@{self.commit_sha[:12]}"
