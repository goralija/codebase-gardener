from __future__ import annotations

from django.db import models

from apps.analysis.fixtures import validate_against_schema
from apps.common.models import UUIDTimestampedModel

PROFILE_SCHEMA_VERSION = "1.0"
DEFAULT_PREFERRED_PR_SIZE = "small"


class GardenerProfile(UUIDTimestampedModel):
    """Learned repo/team memory backing ``.gardener/profile.yaml``.

    The DB row is the source of truth in v1; the repository file is synced by a
    later ticket. Workers read :meth:`to_contract` for ranking signals and
    :func:`apps.profiles.learning.record_pr_outcome` updates the fields below.
    """

    repository = models.OneToOneField(
        "repositories.ManagedRepository",
        on_delete=models.CASCADE,
        related_name="gardener_profile",
    )
    preferred_pr_size = models.CharField(max_length=32, default=DEFAULT_PREFERRED_PR_SIZE)
    accepted_categories = models.JSONField(default=list, blank=True)
    rejected_categories = models.JSONField(default=list, blank=True)
    reverted_categories = models.JSONField(default=list, blank=True)
    learned_protected_patterns = models.JSONField(default=list, blank=True)
    review_preferences = models.JSONField(default=list, blank=True)
    updated_from_pr_outcomes = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"GardenerProfile<{self.repository_id}>"

    @classmethod
    def get_or_create_for_repository(cls, repository) -> "GardenerProfile":
        profile, _ = cls.objects.get_or_create(repository=repository)
        return profile

    def to_contract(self) -> dict:
        contract = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "repository_id": str(self.repository_id),
            "preferred_pr_size": self.preferred_pr_size,
            "accepted_categories": list(self.accepted_categories or []),
            "rejected_categories": list(self.rejected_categories or []),
            "reverted_categories": list(self.reverted_categories or []),
            "learned_protected_patterns": list(self.learned_protected_patterns or []),
            "review_preferences": list(self.review_preferences or []),
            "updated_from_pr_outcomes": list(self.updated_from_pr_outcomes or []),
        }
        validate_against_schema(
            "gardener_profile.schema.json",
            contract,
            label="Gardener profile",
        )
        return contract
