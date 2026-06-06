from celery import shared_task

from apps.github_app.services import process_stored_github_webhook_event


@shared_task
def process_github_webhook_event(webhook_event_id: str) -> dict[str, str]:
    return process_stored_github_webhook_event(webhook_event_id)
