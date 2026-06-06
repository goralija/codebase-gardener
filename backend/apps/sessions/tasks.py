from celery import shared_task
from django.utils import timezone

from apps.analysis import storage_service
from apps.analysis.constitution_pr import maybe_open_constitution_pr
from apps.analysis.runner import AnalysisRunError, run_repository_analysis
from apps.github_app.client import RETRYABLE_STATUS_CODES, GitHubAPIError
from apps.maintenance_prs.docs_fixes import has_docs_actual_fix
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.maintenance_prs.planner import plan_maintenance_prs
from apps.profiles.models import GardenerProfile
from apps.sessions.lifecycle import (
    SessionLifecycleError,
    build_failed_gardening_session_result,
    build_gardening_session_result,
    execute_session_pr_plans,
)
from apps.sessions.models import GardeningSession

MAX_AUTO_APPROVED_SESSION_PLANS = 3


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
        current_phase = "observe"
        _run_foundation_placeholder(session)
        analysis_result = run_repository_analysis(repository=session.repository)
        current_phase = "plan"
        maybe_open_constitution_pr(
            repository=session.repository,
            artifacts=analysis_result.artifacts,
        )
        first_report = storage_service.load_first_report(analysis_result.analysis)
        planned_pr_plans = _plan_session_prs(
            session=session,
            artifacts=analysis_result.artifacts,
            first_report=first_report,
        )
        _approve_auto_executable_pr_plans(planned_pr_plans)
        current_phase = "execute"
        executed_plan_ids, execution_errors = execute_session_pr_plans(session)
        session.result = build_gardening_session_result(
            session,
            started_at=session.started_at,
            executed_plan_ids=executed_plan_ids,
            execution_errors=execution_errors,
            first_report=first_report,
        )
    except AnalysisRunError as exc:
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
    except GitHubAPIError as exc:
        if exc.status_code in RETRYABLE_STATUS_CODES and self.request.retries < self.max_retries:
            session.status = GardeningSession.Status.QUEUED
            session.retry_count = self.request.retries + 1
            session.last_error = str(exc)
            session.save(update_fields=["status", "retry_count", "last_error", "updated_at"])
            raise self.retry(exc=exc, countdown=0)

        session.status = GardeningSession.Status.FAILED
        session.finished_at = timezone.now()
        session.last_error = str(exc)
        session.result = build_failed_gardening_session_result(
            session,
            phase=current_phase,
            message=str(exc),
            started_at=session.started_at,
            finished_at=session.finished_at,
        )
        session.save(update_fields=["status", "finished_at", "result", "last_error", "updated_at"])
        raise
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


def _plan_session_prs(
    *,
    session: GardeningSession,
    artifacts: dict,
    first_report: dict,
) -> list[MaintenancePRPlan]:
    """Persist real PR plans for stored analysis opportunities.

    Fixture reports carry fixture PR plans and a non-UUID demo repository ID,
    so they stay on the legacy fixture path. Stored analysis reports may include
    prior session plan contracts for report serving; those must not suppress
    planning for the current session.
    """
    artifact_opportunities = artifacts.get("opportunities") or []
    if not artifact_opportunities and _is_fixture_report(session, first_report):
        return []

    opportunities = artifact_opportunities or first_report.get("maintenance_opportunities") or []
    if not opportunities:
        return []
    constitution = (
        artifacts.get("constitution")
        if artifact_opportunities
        else first_report.get("repository_constitution")
    ) or {}

    profile = GardenerProfile.get_or_create_for_repository(session.repository).to_contract()
    return plan_maintenance_prs(
        repository=session.repository,
        gardening_session_id=str(session.id),
        opportunities=opportunities,
        constitution=constitution,
        profile=profile,
    )


def _is_fixture_report(session: GardeningSession, first_report: dict) -> bool:
    repository_id = first_report.get("repository_constitution", {}).get("repository_id")
    return repository_id != str(session.repository_id) and bool(
        first_report.get("maintenance_pr_plans")
    )


def _approve_auto_executable_pr_plans(plans: list[MaintenancePRPlan]) -> list[MaintenancePRPlan]:
    approved: list[MaintenancePRPlan] = []
    for _index, plan in sorted(
        enumerate(plans),
        key=lambda item: (0 if has_docs_actual_fix(item[1]) else 1, item[0]),
    ):
        if len(approved) >= MAX_AUTO_APPROVED_SESSION_PLANS:
            break
        if not _safe_for_auto_execution(plan):
            continue
        plan.approval_status = MaintenancePRPlan.ApprovalStatus.APPROVED
        plan.save(update_fields=["approval_status", "updated_at"])
        approved.append(plan)
    return approved


def _safe_for_auto_execution(plan: MaintenancePRPlan) -> bool:
    return (
        not plan.blocked
        and plan.risk_tier == "tier_1_autonomous"
        and plan.confidence >= plan.confidence_threshold
        and plan.repository.is_active
    )
