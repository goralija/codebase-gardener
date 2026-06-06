"""Scheduled trigger dispatch (E04-T02)."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.repositories.models import ManagedRepository
from apps.triggers import registry
from apps.triggers.policy import TriggerNotPermittedError
from apps.triggers.service import SessionEnqueueError, enqueue_session_for_trigger


@shared_task
def dispatch_scheduled_sessions() -> dict[str, int]:
    """Enqueue one scheduled session per active managed repository.

    Run on a Celery beat schedule. The per-period bucket (date) is used as the
    dedup subject so repeated runs within a period do not stack sessions.
    """

    bucket = timezone.now().date().isoformat()
    dispatched = 0
    deduped = 0
    disabled = 0
    failed = 0

    for repository in ManagedRepository.objects.active().iterator():
        try:
            result = enqueue_session_for_trigger(
                repository=repository,
                kind=registry.SCHEDULE,
                subject_type="schedule",
                subject_id=bucket,
                source="schedule",
                extra={"bucket": bucket},
            )
        except TriggerNotPermittedError:
            disabled += 1
            continue
        except SessionEnqueueError:
            failed += 1
            continue
        if result.get("deduped"):
            deduped += 1
        else:
            dispatched += 1

    return {"dispatched": dispatched, "deduped": deduped, "disabled": disabled, "failed": failed}
