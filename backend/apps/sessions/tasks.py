from celery import shared_task
from django.utils import timezone
from gardener_analysis import build_analysis_drift_report

from apps.analysis.models import RepositoryAnalysis
from apps.analysis import storage_service
from apps.analysis.constitution_pr import maybe_open_constitution_pr
from apps.analysis.runner import AnalysisRunError, run_repository_analysis
from apps.common.models import AuditEvent
from apps.github_app.client import RETRYABLE_STATUS_CODES, GitHubAPIError
from apps.maintenance_prs.docs_fixes import has_implemented_file_fix
from apps.maintenance_prs.manual_plans import (
    ManualPlanPayloadError,
    create_manual_session_pr_plan,
)
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
    baseline_analysis = storage_service.get_latest_relevant_baseline(session.repository)
    session.status = GardeningSession.Status.RUNNING
    session.task_id = self.request.id or ""
    session.baseline_analysis = baseline_analysis
    session.started_at = timezone.now()
    session.finished_at = None
    session.last_error = ""
    session.save(
        update_fields=[
            "status",
            "task_id",
            "baseline_analysis",
            "started_at",
            "finished_at",
            "last_error",
            "updated_at",
        ]
    )

    try:
        current_phase = "observe"
        _run_foundation_placeholder(session)
        analysis_result = run_repository_analysis(
            repository=session.repository,
            source=_analysis_source(session),
        )
        session.current_analysis = analysis_result.analysis
        session.save(update_fields=["current_analysis", "updated_at"])

        first_report = storage_service.load_first_report(analysis_result.analysis)
        if _is_first_scan(session):
            maybe_open_constitution_pr(
                repository=session.repository,
                artifacts=analysis_result.artifacts,
            )

        if _baseline_only_session(session, baseline_analysis):
            current_phase = "learn"
            _promote_session_baseline(analysis_result.analysis)
            baseline_only_report = _report_without_pr_work(first_report)
            session.result = build_gardening_session_result(
                session,
                started_at=session.started_at,
                executed_plan_ids=[],
                execution_errors=[],
                first_report=baseline_only_report,
            )
            _emit_completion_notification(session, [])
        else:
            current_phase = "diagnose"
            drift_report = _build_session_drift_report(
                baseline_analysis=baseline_analysis,
                current_analysis=analysis_result.analysis,
                current_artifacts=analysis_result.artifacts,
            )
            session.drift_report = drift_report
            session.save(update_fields=["drift_report", "updated_at"])

            current_phase = "plan"
            drift_opportunities = _drift_relevant_opportunities(
                opportunities=analysis_result.artifacts.get("opportunities") or [],
                drift_report=drift_report,
            )
            planning_artifacts = {
                **analysis_result.artifacts,
                "opportunities": drift_opportunities,
            }
            planning_report = {
                **first_report,
                "maintenance_opportunities": drift_opportunities,
                "maintenance_pr_plans": [],
            }
            planned_pr_plans = _plan_session_prs(
                session=session,
                artifacts=planning_artifacts,
                first_report=planning_report,
            )
            _approve_auto_executable_pr_plans(planned_pr_plans)
            current_phase = "execute"
            executed_plan_ids, execution_errors = execute_session_pr_plans(session)
            session.result = build_gardening_session_result(
                session,
                started_at=session.started_at,
                executed_plan_ids=executed_plan_ids,
                execution_errors=execution_errors,
                first_report=planning_report,
            )
            _promote_session_baseline(analysis_result.analysis)
            _emit_completion_notification(session, executed_plan_ids or [])
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
            phase=current_phase,
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


@shared_task(bind=True, max_retries=3)
def refresh_analysis_after_session_prs(self, session_id: str) -> dict[str, str]:
    session = GardeningSession.objects.select_related(
        "repository",
        "post_pr_refresh_analysis",
    ).get(id=session_id)
    plans = list(
        MaintenancePRPlan.objects.for_session(str(session.id))
        .filter(
            repository=session.repository,
            execution_status=MaintenancePRPlan.ExecutionStatus.SUCCEEDED,
            created_pr_number__isnull=False,
        )
        .order_by("created_at", "id")
    )
    if not plans:
        return {"session_id": str(session.id), "status": "no_authored_prs"}

    terminal_outcomes = {
        MaintenancePRPlan.TerminalOutcome.MERGED,
        MaintenancePRPlan.TerminalOutcome.CLOSED,
        MaintenancePRPlan.TerminalOutcome.REVERTED,
    }
    waiting_plan_ids = [
        str(plan.id)
        for plan in plans
        if plan.terminal_outcome not in terminal_outcomes
        or plan.terminal_outcome_at is None
    ]
    if waiting_plan_ids:
        return {
            "session_id": str(session.id),
            "status": "waiting_for_terminal_prs",
            "waiting_plan_ids": ",".join(waiting_plan_ids),
        }

    latest_terminal_at = max(plan.terminal_outcome_at for plan in plans)
    if (
        session.post_pr_refresh_analysis_id
        and session.post_pr_refresh_analysis
        and session.post_pr_refresh_analysis.created_at >= latest_terminal_at
    ):
        return {"session_id": str(session.id), "status": "already_refreshed"}

    analysis_result = run_repository_analysis(
        repository=session.repository,
        source=RepositoryAnalysis.Source.POST_PR_REFRESH,
    )
    session.post_pr_refresh_analysis = analysis_result.analysis
    session.save(update_fields=["post_pr_refresh_analysis", "updated_at"])
    _promote_session_baseline(analysis_result.analysis)
    return {
        "session_id": str(session.id),
        "status": "refreshed",
        "analysis_id": str(analysis_result.analysis.id),
    }


def _run_foundation_placeholder(session: GardeningSession) -> None:
    simulation = session.trigger.get("simulate")
    if simulation == "retryable_error":
        raise RetryableSessionError("Simulated retryable session error.")


def _analysis_source(session: GardeningSession) -> str:
    if _is_first_scan(session):
        return RepositoryAnalysis.Source.FIRST_SCAN
    return RepositoryAnalysis.Source.SESSION


def _is_first_scan(session: GardeningSession) -> bool:
    return session.trigger.get("type") == "first_scan"


def _baseline_only_session(
    session: GardeningSession,
    baseline_analysis: RepositoryAnalysis | None,
) -> bool:
    return _is_first_scan(session) or baseline_analysis is None


def _promote_session_baseline(analysis: RepositoryAnalysis) -> None:
    storage_service.promote_relevant_baseline(analysis)
    from apps.triggers.service import reset_commit_tracker

    reset_commit_tracker(analysis.repository)


def _report_without_pr_work(first_report: dict) -> dict:
    return {
        **first_report,
        "maintenance_opportunities": [],
        "maintenance_pr_plans": [],
    }


def _build_session_drift_report(
    *,
    baseline_analysis: RepositoryAnalysis,
    current_analysis: RepositoryAnalysis,
    current_artifacts: dict,
) -> dict:
    baseline_snapshot = storage_service.load_snapshot(baseline_analysis) or {
        "repository_id": str(baseline_analysis.repository_id),
        "commit_sha": baseline_analysis.commit_sha,
        "signals": {},
    }
    return build_analysis_drift_report(
        baseline_snapshot=baseline_snapshot,
        baseline_entropy=baseline_analysis.entropy or {},
        current_snapshot=current_artifacts.get("snapshot") or storage_service.load_snapshot(
            current_analysis
        ),
        current_entropy=current_analysis.entropy or {},
        baseline_analysis_id=str(baseline_analysis.id),
        current_analysis_id=str(current_analysis.id),
    )


def _drift_relevant_opportunities(
    *,
    opportunities: list[dict],
    drift_report: dict,
) -> list[dict]:
    changed_signals = [
        *(drift_report.get("signal_changes", {}).get("new") or []),
        *(drift_report.get("signal_changes", {}).get("worsened") or []),
    ]
    drift_paths = {
        str(signal.get("path") or "")
        for signal in changed_signals
        if str(signal.get("path") or "")
    }
    if not drift_paths:
        return []

    relevant: list[dict] = []
    for opportunity in opportunities:
        opportunity_paths = _opportunity_paths(opportunity)
        matched_paths = sorted(
            drift_path
            for drift_path in drift_paths
            if any(_paths_related(opportunity_path, drift_path) for opportunity_path in opportunity_paths)
        )
        if not matched_paths:
            continue
        enriched = {
            **opportunity,
            "evidence": [
                *(opportunity.get("evidence") or []),
                _drift_evidence(drift_report, matched_paths, changed_signals),
            ],
        }
        relevant.append(enriched)
    return relevant


def _opportunity_paths(opportunity: dict) -> set[str]:
    paths = {str(path) for path in opportunity.get("affected_paths", []) if str(path)}
    for evidence in opportunity.get("evidence") or []:
        if isinstance(evidence, dict) and evidence.get("path"):
            paths.add(str(evidence["path"]))
    return paths


def _paths_related(opportunity_path: str, drift_path: str) -> bool:
    from fnmatch import fnmatch

    if opportunity_path == drift_path:
        return True
    return fnmatch(drift_path, opportunity_path) or fnmatch(opportunity_path, drift_path)


def _drift_evidence(
    drift_report: dict,
    matched_paths: list[str],
    changed_signals: list[dict],
) -> dict:
    baseline_commit = drift_report.get("baseline_commit_sha") or "unknown"
    current_commit = drift_report.get("current_commit_sha") or "unknown"
    reasons = [
        str(signal.get("summary") or "")
        for signal in changed_signals
        if signal.get("path") in matched_paths and signal.get("summary")
    ]
    reason = reasons[0] if reasons else "Opportunity touches a drift hotspot."
    return {
        "source_type": "analysis_drift",
        "path": matched_paths[0],
        "summary": (
            f"New or worse since baseline {baseline_commit[:12]} -> "
            f"{current_commit[:12]}: {reason}"
        ),
    }


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
        return _manual_session_pr_plans(session)
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
    ) + _manual_session_pr_plans(session)


def _manual_session_pr_plans(session: GardeningSession) -> list[MaintenancePRPlan]:
    payload = session.trigger.get("manual_plan")
    if not isinstance(payload, dict):
        return []
    try:
        return [create_manual_session_pr_plan(session, payload)]
    except ManualPlanPayloadError:
        return []


def _is_fixture_report(session: GardeningSession, first_report: dict) -> bool:
    repository_id = first_report.get("repository_constitution", {}).get("repository_id")
    return repository_id != str(session.repository_id) and bool(
        first_report.get("maintenance_pr_plans")
    )


def _approve_auto_executable_pr_plans(plans: list[MaintenancePRPlan]) -> list[MaintenancePRPlan]:
    approved: list[MaintenancePRPlan] = []
    for _index, plan in sorted(
        enumerate(plans),
        key=lambda item: (0 if has_implemented_file_fix(item[1]) else 1, item[0]),
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
        and has_implemented_file_fix(plan)
    )


def _emit_completion_notification(
    session: GardeningSession, executed_plan_ids: list
) -> dict:
    """Summarize authored PRs for the user and record an audit event."""
    executed_plan_ids = executed_plan_ids or []
    authored = [
        {
            "maintenance_pr_plan_id": str(plan.id),
            "category": plan.category,
            "risk_tier": plan.risk_tier,
            "pr_number": plan.created_pr_number,
            "pr_url": plan.created_pr_url,
        }
        for plan in MaintenancePRPlan.objects.for_session(str(session.id))
        .filter(created_pr_number__isnull=False)
        .order_by("created_at", "id")
    ]
    notification = {
        "type": "session_completed",
        "repository_id": str(session.repository_id),
        "authored_pr_count": len(authored),
        "review_required": bool(authored),
        "authored_prs": authored,
        "message": (
            f"Gardener authored {len(authored)} maintenance PR(s); review required."
            if authored
            else "Gardener session completed; no PRs authored."
        ),
    }
    try:
        AuditEvent.objects.create(
            organization=session.repository.organization,
            repository=session.repository,
            event_type=AuditEvent.EventType.MAINTENANCE_PRS_AUTHORED,
            source="gardening_worker",
            metadata={
                "gardening_session_id": str(session.id),
                "executed_plan_ids": [str(pid) for pid in executed_plan_ids],
                "notification": notification,
            },
        )
    except Exception:  # noqa: BLE001 - audit failure must not mask session outcome
        pass
    return notification
