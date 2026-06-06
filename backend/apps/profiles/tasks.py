from celery import shared_task

from apps.github_app.client import RETRYABLE_STATUS_CODES, GitHubAPIError
from apps.profiles.models import GardenerProfile
from apps.profiles.sync import sync_profile_to_repo


@shared_task(bind=True, max_retries=3)
def sync_profile_pr(self, repository_id: str) -> dict[str, object]:
    profile = GardenerProfile.objects.get(repository_id=repository_id)
    try:
        result = sync_profile_to_repo(profile)
    except GitHubAPIError as exc:
        if exc.status_code in RETRYABLE_STATUS_CODES and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=0)
        raise

    return {
        "repository_id": str(profile.repository_id),
        "proposed": result.get("proposed", False),
    }
