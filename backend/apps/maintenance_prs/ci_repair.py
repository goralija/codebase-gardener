from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.services import (
    AUTONOMOUS_PR_ADD_ON_DISABLED_REASON,
    autonomous_pr_add_on_enabled,
)
from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError, GitHubAppClient
from apps.github_app.models import GitHubWebhookEvent
from apps.maintenance_prs import ai_fixes
from apps.maintenance_prs.executor import (
    _author_ai_file_fixes,
    _write_updated_file,
)
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.triggers.policy import autonomous_pr_execution_block_reason

CI_REPAIR_AUDIT_SOURCE = "ci_repair_worker"
FAILED_CONCLUSIONS = {"failure", "timed_out", "startup_failure", "action_required"}


class CIRepairError(RuntimeError):
    pass


def repair_failed_maintenance_pr_plan(
    *,
    plan_id: str,
    webhook_event_id: str | None = None,
    client: GitHubAppClient | None = None,
) -> dict[str, Any]:
    plan, attempt = _claim_repair_attempt(plan_id)
    if attempt is None:
        return {
            "maintenance_pr_plan_id": str(plan.id),
            "status": plan.ci_repair_status or "skipped",
            "reason": plan.ci_repair_error or "repair_not_started",
        }

    client = client or GitHubAppClient()
    event = _webhook_event(webhook_event_id)
    try:
        result = _run_repair(plan=plan, attempt=attempt, event=event, client=client)
    except Exception as exc:
        _finish_repair(
            plan,
            status=MaintenancePRPlan.CIRepairStatus.FAILED,
            error=str(exc) or exc.__class__.__name__,
            metadata={"attempt": attempt},
        )
        _audit(
            plan,
            AuditEvent.EventType.MAINTENANCE_PR_CREATION_FAILED,
            {"ci_repair": True, "attempt": attempt, "error": str(exc)},
        )
        raise

    _finish_repair(
        plan,
        status=MaintenancePRPlan.CIRepairStatus.SUCCEEDED,
        error="",
        metadata={"attempt": attempt, **result},
    )
    _audit(
        plan,
        AuditEvent.EventType.MAINTENANCE_PR_CREATED,
        {"ci_repair": True, "attempt": attempt, **result},
    )
    return {
        "maintenance_pr_plan_id": str(plan.id),
        "status": MaintenancePRPlan.CIRepairStatus.SUCCEEDED,
        **result,
    }


def enqueue_ci_repair_for_plan(plan: MaintenancePRPlan, webhook_event_id: str) -> bool:
    if not getattr(settings, "GARDENER_CI_REPAIR_ENABLED", True):
        return False
    if not _eligible_for_repair(plan):
        return False
    from apps.maintenance_prs.tasks import repair_failed_maintenance_pr

    repair_failed_maintenance_pr.delay(str(plan.id), webhook_event_id)
    return True


def _claim_repair_attempt(plan_id: str) -> tuple[MaintenancePRPlan, int | None]:
    with transaction.atomic():
        plan = (
            MaintenancePRPlan.objects.select_for_update()
            .select_related("repository", "repository__organization", "repository__github_installation")
            .get(id=plan_id)
        )
        max_attempts = max(0, int(getattr(settings, "GARDENER_CI_REPAIR_MAX_ATTEMPTS", 1)))
        if not getattr(settings, "GARDENER_CI_REPAIR_ENABLED", True):
            _mark_skipped(plan, "CI repair is disabled.")
            return plan, None
        if not _eligible_for_repair(plan):
            _mark_skipped(plan, _ineligible_reason(plan))
            return plan, None
        if plan.ci_repair_attempts >= max_attempts:
            _mark_skipped(plan, "CI repair attempt limit reached.")
            return plan, None

        attempt = plan.ci_repair_attempts + 1
        history = list(plan.ci_repair_history or [])
        history.append(
            {
                "status": MaintenancePRPlan.CIRepairStatus.RUNNING,
                "attempt": attempt,
                "started_at": _now(),
            }
        )
        plan.ci_repair_attempts = attempt
        plan.ci_repair_status = MaintenancePRPlan.CIRepairStatus.RUNNING
        plan.ci_repair_error = ""
        plan.ci_repair_history = history
        plan.save(
            update_fields=[
                "ci_repair_attempts",
                "ci_repair_status",
                "ci_repair_error",
                "ci_repair_history",
                "updated_at",
            ]
        )
        return plan, attempt


def _run_repair(
    *,
    plan: MaintenancePRPlan,
    attempt: int,
    event: GitHubWebhookEvent | None,
    client: GitHubAppClient,
) -> dict[str, Any]:
    repository = plan.repository
    owner = repository.owner_login
    repo = repository.name
    branch = plan.branch_name
    token = client.create_installation_token(
        repository.github_installation.github_installation_id
    )
    ci_context = _ci_context(client, owner, repo, branch, token=token, event=event)
    file_inputs = _repair_file_inputs(client, owner, repo, branch, token=token, plan=plan)
    if not file_inputs:
        raise CIRepairError("No existing AI-fixable plan files were found on the PR branch.")

    opportunity = {
        "summary": "Repair failed CI checks for this Gardener-authored PR.",
        "evidence": [
            {
                "source_type": "ci_failure",
                "path": path,
                "summary": ci_context["summary"],
            }
            for path, _content in file_inputs
        ],
    }
    updated_files = []
    for path, original, updated in _author_ai_file_fixes(
        file_inputs,
        plan=plan,
        opportunity=opportunity,
    ):
        _write_updated_file(
            client,
            owner,
            repo,
            path=path,
            original=original,
            updated=updated,
            branch=branch,
            token=token,
            plan=plan,
            message=f"Repair failed checks for {plan.title}",
        )
        if updated != original:
            updated_files.append(path)

    if not updated_files:
        raise CIRepairError("AI repair produced no file changes.")

    return {
        "attempt": attempt,
        "updated_paths": updated_files,
        "ci_summary": ci_context["summary"],
    }


def _repair_file_inputs(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    branch: str,
    *,
    token: str,
    plan: MaintenancePRPlan,
) -> list[tuple[str, str]]:
    paths = ai_fixes.ai_fixable_paths(plan)
    file_inputs: list[tuple[str, str]] = []
    for path in paths:
        try:
            content = client.get_file_contents(owner, repo, path, branch=branch, token=token)
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                continue
            raise
        file_inputs.append((path, content))
    return file_inputs


def _ci_context(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    branch: str,
    *,
    token: str,
    event: GitHubWebhookEvent | None,
) -> dict[str, str]:
    payload = event.payload if event is not None else {}
    event_payload = payload.get(event.event) if event is not None else {}
    event_payload = event_payload if isinstance(event_payload, dict) else {}

    log_parts: list[str] = []
    check_names: list[str] = []
    should_read_check_runs = event is None or event.event != "workflow_run"
    if event is not None and event.event == "workflow_run":
        run_id = event_payload.get("id")
        if isinstance(run_id, int):
            try:
                for job in client.list_workflow_run_jobs(owner, repo, run_id, token=token):
                    if job.get("conclusion") not in FAILED_CONCLUSIONS:
                        continue
                    check_names.append(str(job.get("name") or job.get("id") or "workflow job"))
                    job_id = job.get("id")
                    if isinstance(job_id, int):
                        log_parts.append(
                            client.get_workflow_job_logs(owner, repo, job_id, token=token)
                        )
            except GitHubAPIError:
                should_read_check_runs = True
    if should_read_check_runs:
        for check in client.list_check_runs_for_ref(owner, repo, branch, token=token):
            if check.get("conclusion") not in FAILED_CONCLUSIONS:
                continue
            check_names.append(str(check.get("name") or check.get("id") or "check run"))
            output = check.get("output") or {}
            if isinstance(output, dict):
                log_parts.append(
                    "\n".join(
                        str(output.get(key) or "")
                        for key in ("title", "summary", "text")
                        if output.get(key)
                    )
                )

    summary = _truncate_logs(
        "\n\n".join(part for part in log_parts if part.strip())
        or str(event_payload.get("conclusion") or "GitHub check failed.")
    )
    if check_names:
        summary = f"Failed checks: {', '.join(check_names[:5])}.\n{summary}"
    return {"summary": summary}


def _eligible_for_repair(plan: MaintenancePRPlan) -> bool:
    return _ineligible_reason(plan) == ""


def _ineligible_reason(plan: MaintenancePRPlan) -> str:
    if not ai_fixes.has_ai_fix(plan):
        return "Plan category/path is not supported by the AI repair author."
    if plan.blocked:
        return "Plan is blocked."
    if plan.execution_status != MaintenancePRPlan.ExecutionStatus.SUCCEEDED:
        return "Plan has not created a PR successfully."
    if not plan.created_pr_number or not plan.created_pr_url:
        return "Plan has no created PR metadata."
    if plan.terminal_outcome:
        return "Plan PR already has a terminal outcome."
    if not plan.repository.is_active:
        return "Repository is not active."
    automation_block_reason = autonomous_pr_execution_block_reason(plan.repository)
    if automation_block_reason:
        return automation_block_reason
    if not autonomous_pr_add_on_enabled(plan.repository.organization):
        return AUTONOMOUS_PR_ADD_ON_DISABLED_REASON
    return ""


def _mark_skipped(plan: MaintenancePRPlan, reason: str) -> None:
    history = list(plan.ci_repair_history or [])
    history.append(
        {
            "status": MaintenancePRPlan.CIRepairStatus.SKIPPED,
            "reason": reason,
            "recorded_at": _now(),
        }
    )
    plan.ci_repair_status = MaintenancePRPlan.CIRepairStatus.SKIPPED
    plan.ci_repair_error = reason
    plan.ci_repair_history = history
    plan.save(update_fields=["ci_repair_status", "ci_repair_error", "ci_repair_history", "updated_at"])


def _finish_repair(
    plan: MaintenancePRPlan,
    *,
    status: str,
    error: str,
    metadata: dict[str, Any],
) -> None:
    plan.refresh_from_db()
    history = list(plan.ci_repair_history or [])
    history.append(
        {
            "status": status,
            "error": error or None,
            "metadata": metadata,
            "finished_at": _now(),
        }
    )
    plan.ci_repair_status = status
    plan.ci_repair_error = error
    plan.ci_repair_history = history
    plan.save(update_fields=["ci_repair_status", "ci_repair_error", "ci_repair_history", "updated_at"])


def _webhook_event(webhook_event_id: str | None) -> GitHubWebhookEvent | None:
    if not webhook_event_id:
        return None
    return GitHubWebhookEvent.objects.filter(id=webhook_event_id).first()


def _truncate_logs(value: str) -> str:
    limit = max(1000, int(getattr(settings, "GARDENER_CI_REPAIR_LOG_CHARS", 12000)))
    value = " ".join(value.split())
    return value[:limit]


def _audit(plan: MaintenancePRPlan, event_type: str, metadata: dict[str, Any]) -> None:
    AuditEvent.objects.create(
        organization=plan.repository.organization,
        github_installation=plan.repository.github_installation,
        repository=plan.repository,
        event_type=event_type,
        source=CI_REPAIR_AUDIT_SOURCE,
        metadata=metadata,
    )


def _now() -> str:
    return timezone.now().isoformat().replace("+00:00", "Z")
