from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.common.models import AuditEvent
from apps.github_app.client import GitHubAPIError, GitHubAppClient
from apps.maintenance_prs.docs_fixes import (
    apply_docs_maintenance_note,
    docs_actual_fix_paths,
    has_implemented_file_fix,
)
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.maintenance_prs.policy import STALE_RUNNING_TIMEOUT

WORKER_AUDIT_SOURCE = "gardening_worker"


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
) -> dict[str, Any]:
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
) -> list[str]:
    existing_paths: list[str] = []
    for path in docs_actual_fix_paths(plan):
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
        updated = apply_docs_maintenance_note(content, plan)
        if updated == content:
            continue

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
    return existing_paths


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
    if not has_implemented_file_fix(plan):
        raise PlanNotExecutableError(
            "Plan has no implemented autonomous file fix."
        )


def _claim_plan_for_execution(plan: MaintenancePRPlan) -> None:
    stale_running_cutoff = _stale_running_cutoff()
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
