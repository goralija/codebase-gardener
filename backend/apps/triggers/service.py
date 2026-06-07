"""Unified session trigger service (E04-T02).

Single entrypoint that every trigger source (manual, schedule, webhook-derived
push / n_commits / risky_module / pr_opened / ci_failure / first_scan) funnels
through. It applies the permission policy, deduplicates against active sessions,
creates the ``GardeningSession``, enqueues the worker task, and records an audit
event for sensitive kinds.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from django.db.models import F
from django.utils import timezone

from apps.analysis import storage_service
from apps.common.models import AuditEvent
from apps.repositories.models import ManagedRepository
from apps.sessions.models import GardeningSession
from apps.sessions.tasks import run_gardening_session
from apps.triggers import registry
from apps.triggers.models import RepositoryAutomationPolicy, RepositoryCommitTracker
from apps.triggers.policy import ensure_trigger_permitted
from apps.triggers.thresholds import (
    changed_paths_hit_protected,
    commit_threshold,
    configured_commit_threshold,
)

logger = logging.getLogger(__name__)

ACTIVE_SESSION_STATUSES = [
    GardeningSession.Status.QUEUED,
    GardeningSession.Status.RUNNING,
]


class SessionEnqueueError(Exception):
    pass


def enqueue_session_for_trigger(
    *,
    repository: ManagedRepository,
    kind: str,
    subject_type: str,
    subject_id: str,
    source: str,
    extra: dict[str, Any] | None = None,
    actor=None,
) -> dict[str, Any]:
    """Enqueue (or dedupe) a gardening session for a trigger.

    Returns ``{"gardening_session_id", "status", "deduped"}``.
    """

    if kind not in registry.TRIGGER_KINDS:
        raise ValueError(f"Unknown trigger kind: {kind}")

    ensure_trigger_permitted(repository=repository, kind=kind, actor=actor)

    existing = GardeningSession.objects.filter(
        repository=repository,
        status__in=ACTIVE_SESSION_STATUSES,
        trigger__type=kind,
        trigger__subject_type=subject_type,
        trigger__subject_id=subject_id,
    ).first()
    if existing is not None:
        return {
            "gardening_session_id": str(existing.id),
            "status": existing.status,
            "deduped": True,
        }

    trigger = {
        "type": kind,
        "source": source,
        "subject_type": subject_type,
        "subject_id": subject_id,
        **(extra or {}),
    }
    session = GardeningSession.objects.create(repository=repository, trigger=trigger)
    try:
        async_result = run_gardening_session.delay(str(session.id))
    except Exception as exc:
        detail = str(exc) or exc.__class__.__name__
        error = f"Session queue enqueue failed: {detail}"
        failed_at = timezone.now()
        session.status = GardeningSession.Status.FAILED
        session.finished_at = failed_at
        session.last_error = error
        session.result = failed_session_result(session, error, failed_at)
        session.save(
            update_fields=[
                "status",
                "finished_at",
                "last_error",
                "result",
                "updated_at",
            ]
        )
        _record_trigger_failure_audit(
            repository=repository, session=session, kind=kind, actor=actor, error=error
        )
        raise SessionEnqueueError(error) from exc

    task_id = getattr(async_result, "id", "") or ""
    if task_id:
        session.task_id = task_id
        session.save(update_fields=["task_id", "updated_at"])

    _record_trigger_audit(repository=repository, session=session, kind=kind, actor=actor)

    return {
        "gardening_session_id": str(session.id),
        "status": session.status,
        "deduped": False,
    }


def trigger_manual_session(
    *,
    repository: ManagedRepository,
    actor,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lane C service entrypoint for a permission-checked manual trigger."""

    return enqueue_session_for_trigger(
        repository=repository,
        kind=registry.MANUAL,
        subject_type="manual",
        subject_id=str(getattr(actor, "id", "") or "anonymous"),
        source="manual",
        extra=extra,
        actor=actor,
    )


def evaluate_push_triggers(
    *,
    repository: ManagedRepository,
    ref: str,
    payload: dict[str, Any],
    base_trigger_extra: dict[str, Any],
    constitution: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Derive after-N-commits and risky-module sessions from a default-branch push.

    Returns the list of session results produced (may be empty). Callers handle
    the always-on ``push`` session separately to preserve existing behavior.
    """

    constitution = constitution if constitution is not None else constitution_for_repository(repository)
    results: list[dict[str, Any]] = []

    source = base_trigger_extra.get("source", "github_webhook")
    webhook_extra = {key: value for key, value in base_trigger_extra.items() if key != "source"}
    policy = RepositoryAutomationPolicy.get_or_create_for_repository(repository)

    commits = payload.get("commits") or []
    commit_count = len(commits)
    threshold = configured_commit_threshold(constitution) or policy.commit_threshold
    threshold = threshold or commit_threshold(constitution)
    if (
        policy.commit_trigger_enabled
        and commit_count
        and _accumulate_commits(repository, commit_count) >= threshold
    ):
        # Reset before enqueue: a queue failure then under-triggers (safe and
        # self-heals on the next threshold) instead of re-firing every push.
        _reset_commits(repository)
        results.append(
            enqueue_session_for_trigger(
                repository=repository,
                kind=registry.N_COMMITS,
                subject_type="ref",
                subject_id=ref,
                source=source,
                extra={**webhook_extra, "ref": ref},
            )
        )

    changed_paths = changed_paths_from_push(payload)
    reason = changed_paths_hit_protected(changed_paths, constitution)
    if policy.risky_module_trigger_enabled and reason:
        results.append(
            enqueue_session_for_trigger(
                repository=repository,
                kind=registry.RISKY_MODULE,
                subject_type="ref",
                subject_id=ref,
                source=source,
                extra={
                    **webhook_extra,
                    "ref": ref,
                    "reason": reason,
                    "changed_paths": changed_paths[:50],
                },
            )
        )

    return results


def changed_paths_from_push(payload: dict[str, Any]) -> list[str]:
    """Collect the unique set of paths touched by a push payload's commits."""

    paths: list[str] = []
    seen: set[str] = set()
    for commit in payload.get("commits") or []:
        if not isinstance(commit, dict):
            continue
        for field in ("added", "modified", "removed"):
            for path in commit.get(field) or []:
                path = str(path)
                if path and path not in seen:
                    seen.add(path)
                    paths.append(path)
    return paths


def constitution_for_repository(repository: ManagedRepository) -> dict[str, Any]:
    """Return the Repository Constitution for trigger thresholds.

    Trigger rules should use the last promoted repository baseline, not the
    newest unpromoted analysis, because promotion means the default branch state
    has been observed and accepted as the current reference point.
    """

    baseline = storage_service.get_latest_relevant_baseline(repository)
    if baseline is None:
        return {}
    return baseline.constitution or {}


def _accumulate_commits(repository: ManagedRepository, commit_count: int) -> int:
    RepositoryCommitTracker.objects.get_or_create(repository=repository)
    RepositoryCommitTracker.objects.filter(repository=repository).update(
        commits_since_session=F("commits_since_session") + commit_count
    )
    return RepositoryCommitTracker.objects.values_list(
        "commits_since_session", flat=True
    ).get(repository=repository)


def _reset_commits(repository: ManagedRepository) -> None:
    RepositoryCommitTracker.objects.filter(repository=repository).update(commits_since_session=0)


def reset_commit_tracker(repository: ManagedRepository) -> None:
    _reset_commits(repository)


def _record_trigger_audit(
    *,
    repository: ManagedRepository,
    session: GardeningSession,
    kind: str,
    actor,
) -> None:
    if kind not in registry.AUDITED_KINDS:
        return
    _safe_create_audit(
        repository=repository,
        session=session,
        kind=kind,
        actor=actor,
        event_type=AuditEvent.EventType.SESSION_TRIGGER_ENQUEUED,
        extra_metadata=None,
    )


def _record_trigger_failure_audit(
    *,
    repository: ManagedRepository,
    session: GardeningSession,
    kind: str,
    actor,
    error: str,
) -> None:
    # Always audited: a queue failure is a worker failure affecting a customer
    # repository (docs/11 audit requirement).
    _safe_create_audit(
        repository=repository,
        session=session,
        kind=kind,
        actor=actor,
        event_type=AuditEvent.EventType.SESSION_TRIGGER_FAILED,
        extra_metadata={"error": error},
    )


def _safe_create_audit(
    *,
    repository: ManagedRepository,
    session: GardeningSession,
    kind: str,
    actor,
    event_type: str,
    extra_metadata: dict[str, Any] | None,
) -> None:
    """Write an audit event, never letting an audit failure mask the trigger outcome."""

    metadata = {
        "kind": kind,
        "gardening_session_id": str(session.id),
        "subject_id": session.trigger.get("subject_id", ""),
        **(extra_metadata or {}),
    }
    try:
        AuditEvent.objects.create(
            actor=actor if getattr(actor, "pk", None) else None,
            organization=repository.organization,
            github_installation=repository.github_installation,
            repository=repository,
            event_type=event_type,
            source=f"trigger:{kind}",
            metadata=metadata,
        )
    except Exception:
        logger.warning(
            "Failed to write trigger audit event",
            extra={"event_type": event_type, "kind": kind, "repository_id": str(repository.id)},
            exc_info=True,
        )


def failed_session_result(
    session: GardeningSession,
    error: str,
    failed_at: datetime,
) -> dict[str, Any]:
    timestamp = failed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "gardening_session_id": str(session.id),
        "repository_id": str(session.repository_id),
        "trigger": session.trigger,
        "status": "failed",
        "started_at": timestamp,
        "finished_at": timestamp,
        "phase_results": [{"phase": "queue", "status": "failed", "summary": error}],
        "opportunities_selected": [],
        "opportunities_deferred": [],
        "maintenance_pr_plans": [],
        "errors": [{"phase": "queue", "message": error}],
    }
