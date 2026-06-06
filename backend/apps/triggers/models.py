from django.db import models

from apps.common.models import UUIDTimestampedModel


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
