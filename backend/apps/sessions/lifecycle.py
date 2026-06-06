from __future__ import annotations

from datetime import datetime
from datetime import timezone as datetime_timezone
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.analysis.fixtures import load_first_report_fixture
from apps.sessions.models import GardeningSession


PHASES = (
    ("observe", "Loaded shared fixture repository state."),
    ("diagnose", "Diagnosed fixture entropy contributors and opportunities."),
    ("forecast", "Loaded fixture entropy forecast."),
    ("plan", "Selected fixture opportunities and deferred blocked work."),
    ("execute", "Executed approved maintenance PR plans through GitHub."),
    ("learn", "Recorded fixture learning inputs for later outcome handling."),
)


class SessionLifecycleError(Exception):
    def __init__(self, phase: str, message: str) -> None:
        self.phase = phase
        super().__init__(message)


def build_gardening_session_result(
    session: GardeningSession,
    *,
    started_at: datetime,
    finished_at: datetime | None = None,
    executed_plan_ids: list[str] | None = None,
    execution_errors: list[dict[str, str]] | None = None,
    first_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    finished_at = finished_at or timezone.now()
    report = first_report or load_first_report_fixture()
    repository_id = _repository_id(report)
    selected, deferred, plan_ids = _select_fixture_work(report)
    if executed_plan_ids is not None:
        plan_ids = executed_plan_ids
    phase_results = _phase_results()

    fail_phase = _failure_phase(session)
    if fail_phase:
        result = _failed_result(
            session=session,
            repository_id=repository_id,
            started_at=started_at,
            finished_at=finished_at,
            phase=fail_phase,
            message=f"Simulated {fail_phase} phase failure.",
        )
        raise SessionLifecycleError(fail_phase, result["errors"][0]["message"])

    errors = execution_errors or []
    return {
        "schema_version": "1.0",
        "gardening_session_id": str(session.id),
        "repository_id": repository_id,
        "trigger": session.trigger,
        "status": "completed",
        "started_at": _format_timestamp(started_at),
        "finished_at": _format_timestamp(finished_at),
        "phase_results": phase_results,
        "opportunities_selected": selected,
        "opportunities_deferred": deferred,
        "maintenance_pr_plans": plan_ids,
        "errors": errors,
    }


def build_failed_gardening_session_result(
    session: GardeningSession,
    *,
    phase: str,
    message: str,
    started_at: datetime,
    finished_at: datetime | None = None,
) -> dict[str, Any]:
    return _failed_result(
        session=session,
        repository_id=_failure_repository_id(session),
        started_at=started_at,
        finished_at=finished_at or timezone.now(),
        phase=phase,
        message=message,
    )


def _select_fixture_work(fixture: dict[str, Any]) -> tuple[list[str], list[dict[str, str]], list[str]]:
    opportunities = fixture.get("maintenance_opportunities", [])
    plans = fixture.get("maintenance_pr_plans", [])
    plans_by_opportunity: dict[str, list[dict[str, Any]]] = {}
    for plan in plans:
        if plan.get("blocked"):
            continue
        for opportunity_id in plan.get("maintenance_opportunity_ids", []):
            plans_by_opportunity.setdefault(opportunity_id, []).append(plan)

    selected: list[str] = []
    deferred: list[dict[str, str]] = []
    selected_plan_ids: list[str] = []
    for opportunity in opportunities:
        opportunity_id = opportunity.get("maintenance_opportunity_id")
        if not isinstance(opportunity_id, str):
            raise ImproperlyConfigured("Maintenance opportunity fixture is missing an ID.")
        if opportunity.get("blocked_by"):
            deferred.append(
                {
                    "maintenance_opportunity_id": opportunity_id,
                    "reason": "Blocked by another opportunity.",
                }
            )
            continue

        matching_plans = plans_by_opportunity.get(opportunity_id, [])
        if not matching_plans:
            deferred.append(
                {
                    "maintenance_opportunity_id": opportunity_id,
                    "reason": "No matching fixture PR plan.",
                }
            )
            continue

        selected.append(opportunity_id)
        for plan in matching_plans:
            plan_id = plan.get("maintenance_pr_plan_id")
            if isinstance(plan_id, str) and plan_id not in selected_plan_ids:
                selected_plan_ids.append(plan_id)

    return selected, deferred, selected_plan_ids


def _failed_result(
    *,
    session: GardeningSession,
    repository_id: str,
    started_at: datetime,
    finished_at: datetime,
    phase: str,
    message: str,
) -> dict[str, Any]:
    phase_results: list[dict[str, str]] = []
    for phase_name, summary in PHASES:
        if phase_name == phase:
            phase_results.append({"phase": phase_name, "status": "failed", "summary": message})
            break
        phase_results.append({"phase": phase_name, "status": "completed", "summary": summary})

    return {
        "schema_version": "1.0",
        "gardening_session_id": str(session.id),
        "repository_id": repository_id,
        "trigger": session.trigger,
        "status": "failed",
        "started_at": _format_timestamp(started_at),
        "finished_at": _format_timestamp(finished_at),
        "phase_results": phase_results,
        "opportunities_selected": [],
        "opportunities_deferred": [],
        "maintenance_pr_plans": [],
        "errors": [{"phase": phase, "message": message}],
    }


def _phase_results() -> list[dict[str, str]]:
    return [
        {"phase": phase, "status": "completed", "summary": summary}
        for phase, summary in PHASES
    ]


def _failure_phase(session: GardeningSession) -> str:
    if session.trigger.get("simulate") != "failure":
        return ""
    phase = session.trigger.get("fail_phase", "execute")
    phase_names = {phase_name for phase_name, _ in PHASES}
    if phase not in phase_names:
        raise ImproperlyConfigured(f"Unknown simulated failure phase: {phase}")
    return str(phase)


def _repository_id(fixture: dict[str, Any]) -> str:
    repository_id = fixture.get("repository_constitution", {}).get("repository_id")
    if not isinstance(repository_id, str):
        raise ImproperlyConfigured("First report fixture is missing repository_id.")
    return repository_id


def _failure_repository_id(session: GardeningSession) -> str:
    return str(session.repository_id)


def execute_session_pr_plans(
    session: GardeningSession,
) -> tuple[list[str] | None, list[dict[str, str]]]:
    """Execute approved PR plans persisted for this session.

    Returns executed plan IDs and per-plan policy errors. A ``None`` plan list
    means pure fixture mode where no DB plans exist for the session.
    """
    from apps.github_app.client import RETRYABLE_STATUS_CODES, GitHubAPIError
    from apps.maintenance_prs.executor import PRExecutionError, execute_maintenance_pr_plan
    from apps.maintenance_prs.models import MaintenancePRPlan

    plans = list(
        MaintenancePRPlan.objects.for_session(str(session.id)).executable()
    )
    if not plans:
        return None, []

    executed: list[str] = []
    errors: list[dict[str, str]] = []
    for plan in plans:
        try:
            execute_maintenance_pr_plan(plan)
        except GitHubAPIError as exc:
            if exc.status_code in RETRYABLE_STATUS_CODES:
                raise
            errors.append(
                {
                    "phase": "execute",
                    "maintenance_pr_plan_id": str(plan.id),
                    "message": str(exc),
                }
            )
            continue
        except PRExecutionError as exc:
            errors.append(
                {
                    "phase": "execute",
                    "maintenance_pr_plan_id": str(plan.id),
                    "message": str(exc),
                }
            )
            continue
        executed.append(str(plan.id))
    return executed, errors


def _format_timestamp(value: datetime) -> str:
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone=datetime_timezone.utc)
    return value.astimezone(datetime_timezone.utc).isoformat().replace("+00:00", "Z")
