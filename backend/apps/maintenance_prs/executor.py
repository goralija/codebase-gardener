from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.billing.services import (
    AUTONOMOUS_PR_ADD_ON_DISABLED_REASON,
    autonomous_pr_add_on_enabled,
)
from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError, GitHubAppClient
from apps.maintenance_prs import ai_fixes
from apps.maintenance_prs.docs_fixes import (
    apply_docs_maintenance_note,
    docs_actual_fix_paths,
    has_implemented_file_fix,
)
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.maintenance_prs.policy import STALE_RUNNING_TIMEOUT
from apps.triggers.models import RepositoryAutomationPolicy
from apps.triggers.policy import autonomous_pr_execution_block_reason

WORKER_AUDIT_SOURCE = "gardening_worker"
DEFAULT_AI_FIX_WORKERS = 8


class PRExecutionError(Exception):
    pass


class PlanNotExecutableError(PRExecutionError):
    pass


_SECTION_ORDER = (
    ("goal", "Goal"),
    ("evidence", "Evidence"),
    ("entropy_impact", "Entropy impact"),
    ("verification", "Verification"),
    ("roi_impact", "ROI impact"),
)


def render_pr_body(plan: MaintenancePRPlan) -> str:
    sections = plan.pr_body_sections or {}
    lines: list[str] = []
    for key, heading in _SECTION_ORDER:
        value = sections.get(key)
        if value:
            lines.append(f"## {heading}\n\n{value}")
    return "\n\n".join(lines)


def execute_maintenance_pr_plan(
    plan: MaintenancePRPlan,
    *,
    client: GitHubAppClient | None = None,
    progress=None,
) -> dict[str, Any]:
    # ``progress(percent, phase, message)`` is forwarded to the AI author so
    # callers can surface how far along a fix is.
    # TODO(frontend/backend): pass a progress callback from run_gardening_session
    # that calls self.update_state(state="PROGRESS", meta={"percent", "phase",
    # "message", "plan_id"}) so the dashboard can render a live progress bar
    # (poll the Celery task id), or persist it on the plan for the API to expose.
    _guard_executable(plan)
    _claim_plan_for_execution(plan)

    client = client or GitHubAppClient()
    repository = plan.repository
    installation = repository.github_installation
    owner = repository.owner_login
    repo = repository.name
    base_branch = repository.default_branch
    branch = plan.branch_name

    try:
        token = client.create_installation_token(installation.github_installation_id)

        base_sha = client.get_branch_ref(owner, repo, base_branch, token=token)
        body = render_pr_body(plan)
        marker_path = f".gardener/plans/{_marker_filename(branch)}"
        marker_content = _marker_content(plan, body)
        try:
            client.create_branch_ref(owner, repo, branch=branch, sha=base_sha, token=token)
        except GitHubAPIError as exc:
            # 422 = reference already exists; tolerate only if marker proves same plan.
            if exc.status_code != 422:
                raise
            _verify_existing_branch_belongs_to_plan(
                client,
                owner,
                repo,
                marker_path=marker_path,
                branch=branch,
                token=token,
                plan=plan,
            )

        _put_marker_file(
            client,
            owner,
            repo,
            marker_path=marker_path,
            marker_content=marker_content,
            branch=branch,
            token=token,
            plan=plan,
        )
        actual_fix_paths = _apply_actual_file_fixes(
            client,
            owner,
            repo,
            branch=branch,
            token=token,
            plan=plan,
            progress=progress,
        )
        if not actual_fix_paths:
            raise PlanNotExecutableError(
                "Docs plan did not find any existing safe Markdown file to update."
            )

        pull_request = _create_or_find_pull_request(
            client,
            owner,
            repo,
            title=plan.title,
            head=branch,
            base=base_branch,
            body=body,
            token=token,
        )
        pr_number, pr_url = _validated_pull_request_result(pull_request)
        _apply_risk_labels(client, owner, repo, pr_number, plan, token=token)
    except Exception as exc:
        plan.execution_status = MaintenancePRPlan.ExecutionStatus.FAILED
        plan.execution_error = str(exc)
        with transaction.atomic():
            plan.save(update_fields=["execution_status", "execution_error", "updated_at"])
            _audit(
                plan,
                AuditEvent.EventType.MAINTENANCE_PR_CREATION_FAILED,
                {"error": str(exc)},
            )
        raise

    plan.created_pr_number = pr_number
    plan.created_pr_url = pr_url
    plan.created_branch_ref = f"refs/heads/{branch}"
    plan.execution_status = MaintenancePRPlan.ExecutionStatus.SUCCEEDED
    plan.execution_error = ""
    with transaction.atomic():
        plan.save(
            update_fields=[
                "created_pr_number",
                "created_pr_url",
                "created_branch_ref",
                "execution_status",
                "execution_error",
                "updated_at",
            ]
        )
        _audit(
            plan,
            AuditEvent.EventType.MAINTENANCE_PR_CREATED,
            {
                "pr_number": plan.created_pr_number,
                "pr_url": plan.created_pr_url,
                "branch_ref": plan.created_branch_ref,
            },
        )

    return {
        "maintenance_pr_plan_id": str(plan.id),
        "execution_status": plan.execution_status,
        "created_pr_number": plan.created_pr_number,
        "created_pr_url": plan.created_pr_url,
    }


def _create_or_find_pull_request(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    *,
    title: str,
    head: str,
    base: str,
    body: str,
    token: str,
) -> dict[str, Any]:
    try:
        return client.create_pull_request(
            owner, repo, title=title, head=head, base=base, body=body, token=token
        )
    except GitHubAPIError as exc:
        # 422 = a PR already exists for this head; reuse it for idempotent re-runs.
        if exc.status_code != 422:
            raise
        existing = client.find_pull_request(
            owner, repo, head=head, base=base, token=token
        )
        if existing is None:
            raise
        return existing


def _validated_pull_request_result(pull_request: dict[str, Any]) -> tuple[int, str]:
    pr_number = pull_request.get("number")
    pr_url = pull_request.get("html_url")
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise GitHubAPIError("GitHub pull request response did not include a valid number.")
    if not isinstance(pr_url, str) or not pr_url:
        raise GitHubAPIError("GitHub pull request response did not include a valid html_url.")
    return pr_number, pr_url


def _apply_actual_file_fixes(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    *,
    branch: str,
    token: str,
    plan: MaintenancePRPlan,
    progress=None,
) -> list[str]:
    if plan.category == "docs":
        paths = docs_actual_fix_paths(plan)
        opportunity = {}
    else:
        paths = ai_fixes.ai_fixable_paths(plan)
        opportunity = _lookup_opportunity(plan)

    existing_paths: list[str] = []
    file_inputs: list[tuple[str, str]] = []
    for path in paths:
        try:
            content = client.get_file_contents(
                owner,
                repo,
                path,
                branch=branch,
                token=token,
            )
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                continue
            raise

        existing_paths.append(path)
        if plan.category == "docs":
            updated = apply_docs_maintenance_note(content, plan)
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 58a0c24 (fix(ai-fixes): apply edit blocks best-effort instead of all-or-nothing)
            _write_updated_file(
                client,
                owner,
                repo,
                path=path,
                original=content,
                updated=updated,
                branch=branch,
                token=token,
                plan=plan,
            )
<<<<<<< HEAD
=======
        else:
            updated = apply_ai_fix(path, content, plan, opportunity, progress=progress)
        if updated == content:
>>>>>>> 9e7c4e4 (feat(ai-fixes): progress logging + percentage callback for AI authoring)
=======
>>>>>>> 58a0c24 (fix(ai-fixes): apply edit blocks best-effort instead of all-or-nothing)
            continue
        file_inputs.append((path, content))

    if plan.category != "docs" and file_inputs:
        for path, original, updated in _author_ai_file_fixes(
            file_inputs,
            plan=plan,
            opportunity=opportunity,
            progress=progress,
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
            )
    return existing_paths


def _author_ai_file_fixes(
    file_inputs: list[tuple[str, str]],
    *,
    plan: MaintenancePRPlan,
    opportunity: dict,
    progress=None,
) -> list[tuple[str, str, str]]:
    workers = min(_ai_fix_worker_count(), len(file_inputs))
    if workers <= 1:
        return [
            (
                path,
                content,
                ai_fixes.apply_ai_fix(
                    path, content, plan, opportunity, progress=progress
                ),
            )
            for path, content in file_inputs
        ]

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                ai_fixes.apply_ai_fix,
                path,
                content,
                plan,
                opportunity,
                progress,
            ): path
            for path, content in file_inputs
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    return [(path, content, results[path]) for path, content in file_inputs]


def _ai_fix_worker_count() -> int:
    raw = os.getenv("GARDENER_AI_FIX_WORKERS", str(DEFAULT_AI_FIX_WORKERS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_AI_FIX_WORKERS
    return max(1, min(value, DEFAULT_AI_FIX_WORKERS))


def _write_updated_file(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    *,
    path: str,
    original: str,
    updated: str,
    branch: str,
    token: str,
    plan: MaintenancePRPlan,
) -> None:
    if updated == original:
        return

    sha = client.get_file_sha(owner, repo, path, branch=branch, token=token)
    client.put_file_contents(
        owner,
        repo,
        path,
        message=plan.title,
        content=updated,
        branch=branch,
        token=token,
        sha=sha,
    )


def _risk_labels(plan: MaintenancePRPlan) -> list[str]:
    """Reviewer-facing labels: risk tier, confidence band, category."""
    tier = (plan.risk_tier or "unknown").replace("_", "-")
    if plan.confidence >= 0.9:
        band = "high"
    elif plan.confidence >= 0.7:
        band = "medium"
    else:
        band = "low"
    labels = [f"gardener:{tier}", f"gardener:confidence-{band}"]
    if plan.category:
        labels.append(f"gardener:category-{plan.category.replace('_', '-')}")
    return labels


def _apply_risk_labels(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    pr_number: int,
    plan: MaintenancePRPlan,
    *,
    token: str,
) -> None:
    """Best-effort: never fail PR creation if labeling errors."""
    try:
        client.add_labels(owner, repo, pr_number, _risk_labels(plan), token=token)
    except Exception:  # noqa: BLE001 - labeling is non-critical
        pass


def _lookup_opportunity(plan: MaintenancePRPlan) -> dict:
    """Find the source opportunity for this plan in the latest stored analysis."""
    from apps.analysis import storage_service

    opportunity_ids = set(
        plan.opportunity_links.values_list("maintenance_opportunity_id", flat=True)
    )
    if not opportunity_ids:
        return {}
    analysis = storage_service.get_latest(plan.repository)
    if analysis is None:
        return {}
    for opportunity in analysis.opportunities or []:
        if (
            isinstance(opportunity, dict)
            and opportunity.get("maintenance_opportunity_id") in opportunity_ids
        ):
            return opportunity
    return {}


def _put_marker_file(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    *,
    marker_path: str,
    marker_content: str,
    branch: str,
    token: str,
    plan: MaintenancePRPlan,
) -> None:
    marker_sha = client.get_file_sha(
        owner,
        repo,
        marker_path,
        branch=branch,
        token=token,
    )
    client.put_file_contents(
        owner,
        repo,
        marker_path,
        message=plan.title,
        content=marker_content,
        branch=branch,
        token=token,
        sha=marker_sha,
    )


def _marker_content(plan: MaintenancePRPlan, body: str) -> str:
    return (
        f"<!-- gardener-maintenance-pr-plan-id: {plan.id} -->\n"
        f"# {plan.title}\n\n{body}\n"
    )


def _verify_existing_branch_belongs_to_plan(
    client: GitHubAppClient,
    owner: str,
    repo: str,
    *,
    marker_path: str,
    branch: str,
    token: str,
    plan: MaintenancePRPlan,
) -> None:
    try:
        marker = client.get_file_contents(
            owner,
            repo,
            marker_path,
            branch=branch,
            token=token,
        )
    except GitHubAPIError as exc:
        if exc.status_code == 404:
            raise PlanNotExecutableError(
                "Branch already exists and does not belong to this maintenance PR plan."
            ) from exc
        raise
    if f"gardener-maintenance-pr-plan-id: {plan.id}" not in marker:
        raise PlanNotExecutableError(
            "Branch already exists and does not belong to this maintenance PR plan."
        )


def _guard_executable(plan: MaintenancePRPlan) -> None:
    if plan.blocked:
        raise PlanNotExecutableError("Plan is blocked and cannot be executed.")
    if plan.approval_status != MaintenancePRPlan.ApprovalStatus.APPROVED:
        raise PlanNotExecutableError("Plan is not approved for execution.")
    if plan.execution_status == MaintenancePRPlan.ExecutionStatus.SUCCEEDED:
        raise PlanNotExecutableError("Plan has already been executed.")
    if (
        plan.execution_status == MaintenancePRPlan.ExecutionStatus.RUNNING
        and plan.updated_at >= _stale_running_cutoff()
    ):
        raise PlanNotExecutableError("Plan is already running.")
    if plan.risk_tier != "tier_1_autonomous":
        raise PlanNotExecutableError(
            "Only tier_1_autonomous plans can be executed autonomously."
        )
    if plan.confidence < plan.confidence_threshold:
        raise PlanNotExecutableError(
            f"Plan confidence {plan.confidence:.2f} is below the "
            f"{plan.confidence_threshold:.2f} PR creation threshold."
        )
    if not plan.repository.is_active:
        raise PlanNotExecutableError(
            "Plan repository is not active (unselected, suspended, or deactivated)."
        )
    automation_block_reason = autonomous_pr_execution_block_reason(plan.repository)
    if automation_block_reason:
        raise PlanNotExecutableError(automation_block_reason)
    if not autonomous_pr_add_on_enabled(plan.repository.organization):
        raise PlanNotExecutableError(AUTONOMOUS_PR_ADD_ON_DISABLED_REASON)
    if not has_implemented_file_fix(plan):
        raise PlanNotExecutableError(
            "Plan has no implemented autonomous file fix."
        )


def _claim_plan_for_execution(plan: MaintenancePRPlan) -> None:
    stale_running_cutoff = _stale_running_cutoff()
    RepositoryAutomationPolicy.get_or_create_for_repository(plan.repository)
    updated = MaintenancePRPlan.objects.filter(
        pk=plan.pk,
        blocked=False,
        approval_status=MaintenancePRPlan.ApprovalStatus.APPROVED,
        risk_tier="tier_1_autonomous",
        confidence__gte=F("confidence_threshold"),
        repository__unselected_at__isnull=True,
        repository__deleted_at__isnull=True,
        repository__organization__deactivated_at__isnull=True,
        repository__github_installation__suspended_at__isnull=True,
        repository__github_installation__deleted_at__isnull=True,
        repository__github_installation__organization_id=F("repository__organization_id"),
        repository__automation_policy__autonomy_mode=(
            RepositoryAutomationPolicy.AutonomyMode.AUTONOMOUS
        ),
        repository__organization__subscription__autonomous_pr_add_on_enabled=True,
    ).filter(
        Q(
            execution_status__in=[
                MaintenancePRPlan.ExecutionStatus.PENDING,
                MaintenancePRPlan.ExecutionStatus.FAILED,
            ]
        )
        | Q(
            execution_status=MaintenancePRPlan.ExecutionStatus.RUNNING,
            updated_at__lt=stale_running_cutoff,
        )
    ).update(
        execution_status=MaintenancePRPlan.ExecutionStatus.RUNNING,
        execution_error="",
        updated_at=timezone.now(),
    )
    if updated != 1:
        plan.refresh_from_db()
        raise PlanNotExecutableError("Plan could not be claimed for execution.")
    plan.refresh_from_db()


def _marker_filename(branch: str) -> str:
    return f"{branch.replace('/', '-')}.md"


def _stale_running_cutoff():
    return timezone.now() - STALE_RUNNING_TIMEOUT


def _audit(
    plan: MaintenancePRPlan,
    event_type: str,
    metadata: dict[str, Any],
) -> None:
    repository = plan.repository
    AuditEvent.objects.create(
        organization=repository.organization,
        github_installation=repository.github_installation,
        repository=repository,
        event_type=event_type,
        source=WORKER_AUDIT_SOURCE,
        metadata={"maintenance_pr_plan_id": str(plan.id), **metadata},
    )
