"""Scheduled trigger dispatch (E04-T02)."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.repositories.models import ManagedRepository
from apps.sessions.models import GardeningSession
from apps.sessions.tasks import run_gardening_session
from apps.triggers import registry
from apps.triggers.policy import TriggerNotPermittedError
from apps.triggers.service import SessionEnqueueError, enqueue_session_for_trigger

logger = logging.getLogger(__name__)


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


@shared_task
def requeue_orphaned_sessions() -> dict[str, int]:
    """Re-dispatch sessions stranded by a worker/broker outage.

    Two orphan shapes are recovered:

    * **QUEUED** rows whose Celery message was lost before any worker picked
      them up (the row never starts because no message remains in the broker).
    * **RUNNING** zombies whose worker died mid-task: ``started_at`` is set but
      ``updated_at`` has not advanced (no progress event) past the stale window,
      so the task is dead yet the row never re-queues.

    Both are re-issued via ``run_gardening_session`` (idempotent: it re-loads the
    session and restarts the pipeline).
    """

    now = timezone.now()
    queued_cutoff = now - timedelta(
        seconds=getattr(settings, "ORPHANED_SESSION_GRACE_SECONDS", 120)
    )
    running_cutoff = now - timedelta(
        seconds=getattr(settings, "STALE_RUNNING_SESSION_SECONDS", 900)
    )
    stuck = GardeningSession.objects.filter(
        Q(
            status=GardeningSession.Status.QUEUED,
            started_at__isnull=True,
            updated_at__lt=queued_cutoff,
        )
        | Q(
            status=GardeningSession.Status.RUNNING,
            updated_at__lt=running_cutoff,
        )
    )
    requeued = 0
    for session in stuck.iterator():
        run_gardening_session.delay(str(session.id))
        requeued += 1
    if requeued:
        logger.info("triggers.requeue_orphaned_sessions", extra={"requeued": requeued})
    return {"requeued": requeued}
