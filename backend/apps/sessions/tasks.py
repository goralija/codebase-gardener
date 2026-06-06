from celery import shared_task
from django.utils import timezone

from apps.sessions.lifecycle import (
    SessionLifecycleError,
    build_failed_gardening_session_result,
    build_gardening_session_result,
)
from apps.sessions.models import GardeningSession


class RetryableSessionError(Exception):
    pass


@shared_task(bind=True, max_retries=3)
def run_gardening_session(self, session_id: str) -> dict[str, str]:
    session = GardeningSession.objects.get(id=session_id)
    session.status = GardeningSession.Status.RUNNING
    session.task_id = self.request.id or ""
    session.started_at = timezone.now()
    session.finished_at = None
    session.last_error = ""
    session.save(
        update_fields=[
            "status",
            "task_id",
            "started_at",
            "finished_at",
            "last_error",
            "updated_at",
        ]
    )

    try:
        _run_foundation_placeholder(session)
        session.result = build_gardening_session_result(
            session,
            started_at=session.started_at,
        )
    except SessionLifecycleError as exc:
        session.status = GardeningSession.Status.FAILED
        session.finished_at = timezone.now()
        session.result = build_failed_gardening_session_result(
            session,
            phase=exc.phase,
            message=str(exc),
            started_at=session.started_at,
            finished_at=session.finished_at,
        )
        session.last_error = str(exc)
        session.save(
            update_fields=[
                "status",
                "finished_at",
                "result",
                "last_error",
                "updated_at",
            ]
        )
        raise
    except RetryableSessionError as exc:
        if self.request.retries >= self.max_retries:
            session.status = GardeningSession.Status.FAILED
            session.retry_count = self.request.retries
            session.finished_at = timezone.now()
            session.last_error = str(exc)
            session.result = build_failed_gardening_session_result(
                session,
                phase="observe",
                message=str(exc),
                started_at=session.started_at,
                finished_at=session.finished_at,
            )
            session.save(
                update_fields=[
                    "status",
                    "retry_count",
                    "finished_at",
                    "result",
                    "last_error",
                    "updated_at",
                ]
            )
            raise

        session.status = GardeningSession.Status.QUEUED
        session.retry_count = self.request.retries + 1
        session.last_error = str(exc)
        session.save(update_fields=["status", "retry_count", "last_error", "updated_at"])
        raise self.retry(exc=exc, countdown=0)
    except Exception as exc:
        session.status = GardeningSession.Status.FAILED
        session.finished_at = timezone.now()
        session.last_error = str(exc)
        session.result = build_failed_gardening_session_result(
            session,
            phase="observe",
            message=str(exc),
            started_at=session.started_at,
            finished_at=session.finished_at,
        )
        session.save(update_fields=["status", "finished_at", "result", "last_error", "updated_at"])
        raise

    session.status = GardeningSession.Status.COMPLETED
    session.finished_at = timezone.now()
    session.last_error = ""
    session.result["status"] = "completed"
    session.result["finished_at"] = session.finished_at.isoformat().replace("+00:00", "Z")
    session.save(update_fields=["status", "finished_at", "result", "last_error", "updated_at"])
    return {"session_id": str(session.id), "status": session.status}


def _run_foundation_placeholder(session: GardeningSession) -> None:
    simulation = session.trigger.get("simulate")
    if simulation == "retryable_error":
        raise RetryableSessionError("Simulated retryable session error.")
