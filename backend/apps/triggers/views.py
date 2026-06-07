from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.analysis import storage_service
from apps.accounts.models import Membership
from apps.billing.services import (
    AUTONOMOUS_PR_ADD_ON_DISABLED_REASON,
    autonomous_pr_add_on_enabled,
)
from apps.common.api import api_error_response
from apps.common.models import AuditEvent
from apps.maintenance_prs.manual_plans import (
    ManualPlanPayloadError,
    normalize_manual_plan_payload,
)
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.maintenance_prs.policy import DEFAULT_CONFIDENCE_THRESHOLD
from apps.repositories.models import ManagedRepository
from apps.sessions.models import GardeningSession
from apps.triggers.models import RepositoryAutomationPolicy
from apps.triggers.policy import (
    TriggerNotPermittedError,
    autonomous_pr_execution_block_reason,
)
from apps.triggers.serializers import RepositoryAutomationPolicySerializer
from apps.triggers import registry
from apps.triggers.service import (
    SessionEnqueueError,
    enqueue_session_for_trigger,
    trigger_manual_session,
)
from apps.triggers.thresholds import DEFAULT_COMMIT_THRESHOLD


AUTOMATION_EDIT_ROLES = {
    Membership.Role.OWNER,
    Membership.Role.ADMIN,
    Membership.Role.MAINTAINER,
}


@api_view(["GET", "PATCH"])
def repository_automation(request, organization_id, repository_id):
    repository = _visible_repository(request.user, organization_id, repository_id)
    if repository is None:
        return api_error_response(
            "not_found",
            "Repository not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    policy = RepositoryAutomationPolicy.get_or_create_for_repository(repository)

    if request.method == "PATCH":
        if not _can_edit_automation(request.user, repository.organization):
            return api_error_response(
                "permission_denied",
                "Owner, admin, or maintainer access is required to update automation.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        previous = _policy_values(policy)
        serializer = RepositoryAutomationPolicySerializer(policy, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            return api_error_response(
                "validation_error",
                "At least one automation field is required.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        policy = serializer.save()
        _audit_policy_update(
            actor=request.user,
            repository=repository,
            previous=previous,
            current=_policy_values(policy),
        )

    return Response(_automation_payload(repository, request.user))


@api_view(["POST"])
def repository_automation_trigger(request, organization_id, repository_id):
    repository = _visible_repository(request.user, organization_id, repository_id)
    if repository is None:
        return api_error_response(
            "not_found",
            "Repository not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if not _can_edit_automation(request.user, repository.organization):
        return api_error_response(
            "permission_denied",
            "Owner, admin, or maintainer access is required to trigger a session.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    extra = {"source_view": "repository_automation"}
    manual_plan = _manual_plan_from_request(request.data)
    if isinstance(manual_plan, Response):
        return manual_plan
    if manual_plan is not None:
        extra["manual_plan"] = manual_plan

    try:
        if _should_run_first_scan(repository, manual_plan):
            result = enqueue_session_for_trigger(
                repository=repository,
                kind=registry.FIRST_SCAN,
                subject_type="repository",
                subject_id=str(repository.id),
                source="first_scan",
                extra=extra,
                actor=request.user,
            )
        else:
            result = trigger_manual_session(
                repository=repository,
                actor=request.user,
                extra=extra,
            )
    except TriggerNotPermittedError as exc:
        return api_error_response(
            "trigger_not_permitted",
            str(exc),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except SessionEnqueueError as exc:
        return api_error_response(
            "session_enqueue_failed",
            str(exc),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"trigger": result}, status=status.HTTP_202_ACCEPTED)


def _should_run_first_scan(repository, manual_plan) -> bool:
    return manual_plan is None and not repository.gardening_sessions.exists()


def _manual_plan_from_request(data):
    if not isinstance(data, dict):
        return None
    raw = data.get("manual_plan")
    if raw is None:
        return None
    try:
        return normalize_manual_plan_payload(raw)
    except ManualPlanPayloadError as exc:
        return api_error_response(
            "validation_error",
            str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def _automation_payload(repository, user):
    policy = RepositoryAutomationPolicy.get_or_create_for_repository(repository)
    add_on_enabled = autonomous_pr_add_on_enabled(repository.organization)
    automation_block_reason = autonomous_pr_execution_block_reason(repository)
    pr_creation_block_reason = None
    if automation_block_reason:
        pr_creation_block_reason = automation_block_reason
    elif not add_on_enabled:
        pr_creation_block_reason = AUTONOMOUS_PR_ADD_ON_DISABLED_REASON

    can_create_autonomous_prs = pr_creation_block_reason is None

    return {
        "schema_version": "1.0",
        "repository": _repository_payload(repository),
        "baseline": _baseline_payload(repository),
        "stats": _repository_stats_payload(repository),
        "policy": RepositoryAutomationPolicySerializer(policy).data,
        "effective": {
            "autonomous_pr_add_on_enabled": add_on_enabled,
            "can_create_autonomous_prs": can_create_autonomous_prs,
            "pr_creation_status": (
                "Autonomous PR creation is enabled."
                if can_create_autonomous_prs
                else pr_creation_block_reason
            ),
            "default_commit_threshold": DEFAULT_COMMIT_THRESHOLD,
            "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
        },
        "permissions": {
            "can_edit": _can_edit_automation(user, repository.organization),
            "can_trigger_manual_session": _can_edit_automation(user, repository.organization),
        },
        "recent_sessions": [
            _session_payload(session)
            for session in repository.gardening_sessions.order_by("-created_at")[:5]
        ],
        "recent_pr_plans": [
            _pr_plan_payload(plan)
            for plan in repository.maintenance_pr_plans.order_by("-created_at")[:5]
        ],
    }


def _visible_repository(user, organization_id, repository_id):
    if not getattr(user, "is_active", False):
        return None

    queryset = ManagedRepository.objects.active().select_related(
        "organization",
        "github_installation",
    )
    if getattr(user, "is_staff", False):
        return queryset.filter(id=repository_id, organization_id=organization_id).first()

    return (
        ManagedRepository.objects.visible_to(user)
        .select_related("organization", "github_installation")
        .filter(id=repository_id, organization_id=organization_id)
        .first()
    )


def _can_edit_automation(user, organization) -> bool:
    if getattr(user, "is_staff", False):
        return True
    return Membership.objects.active().filter(
        user=user,
        organization=organization,
        role__in=AUTOMATION_EDIT_ROLES,
    ).exists()


def _repository_payload(repository):
    return {
        "id": str(repository.id),
        "full_name": repository.full_name,
        "default_branch": repository.default_branch,
        "html_url": repository.html_url,
    }


def _baseline_payload(repository):
    baseline = storage_service.get_latest_relevant_baseline(repository)
    if baseline is None:
        return {
            "analysis_id": None,
            "commit_sha": None,
            "source": None,
            "promoted_at": None,
        }
    return {
        "analysis_id": str(baseline.id),
        "commit_sha": baseline.commit_sha,
        "source": baseline.source,
        "promoted_at": _timestamp(baseline.baseline_promoted_at),
    }


def _repository_stats_payload(repository):
    analyses = repository.analyses
    sessions = repository.gardening_sessions
    pr_plans = repository.maintenance_pr_plans
    latest_report_at = (
        analyses.order_by("-created_at").values_list("created_at", flat=True).first()
    )

    return {
        "report_count": analyses.count(),
        "session_count": sessions.count(),
        "completed_session_count": sessions.filter(
            status=GardeningSession.Status.COMPLETED
        ).count(),
        "pr_plan_count": pr_plans.count(),
        "created_pr_count": pr_plans.exclude(created_pr_url="").count(),
        "merged_pr_count": pr_plans.filter(
            terminal_outcome=MaintenancePRPlan.TerminalOutcome.MERGED
        ).count(),
        "blocked_pr_count": pr_plans.filter(blocked=True).count(),
        "latest_report_at": _timestamp(latest_report_at),
    }


def _session_payload(session: GardeningSession):
    return {
        "id": str(session.id),
        "status": session.status,
        "trigger": session.trigger,
        "baseline_analysis_id": str(session.baseline_analysis_id)
        if session.baseline_analysis_id
        else None,
        "current_analysis_id": str(session.current_analysis_id)
        if session.current_analysis_id
        else None,
        "current_commit_sha": session.current_analysis.commit_sha
        if session.current_analysis_id
        else None,
        "has_drift_report": bool(session.drift_report),
        "created_at": _timestamp(session.created_at),
        "started_at": _timestamp(session.started_at),
        "finished_at": _timestamp(session.finished_at),
        "last_error": session.last_error,
    }


def _pr_plan_payload(plan: MaintenancePRPlan):
    return {
        "id": str(plan.id),
        "title": plan.title,
        "blocked": plan.blocked,
        "block_reason": plan.block_reason,
        "approval_status": plan.approval_status,
        "execution_status": plan.execution_status,
        "created_pr_url": plan.created_pr_url or None,
        "terminal_outcome": plan.terminal_outcome or None,
        "terminal_outcome_at": _timestamp(plan.terminal_outcome_at),
        "confidence": plan.confidence,
        "confidence_threshold": plan.confidence_threshold,
        "created_at": _timestamp(plan.created_at),
    }


def _timestamp(value):
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _policy_values(policy):
    return {
        field: getattr(policy, field)
        for field in RepositoryAutomationPolicySerializer.Meta.fields
        if field not in {"id", "created_at", "updated_at"}
    }


def _audit_policy_update(*, actor, repository, previous, current) -> None:
    changed_fields = [
        field
        for field, previous_value in previous.items()
        if current.get(field) != previous_value
    ]
    if not changed_fields:
        return

    AuditEvent.objects.create(
        actor=actor,
        organization=repository.organization,
        github_installation=repository.github_installation,
        repository=repository,
        event_type=AuditEvent.EventType.AUTOMATION_POLICY_UPDATED,
        source="repository_automation_api",
        metadata={
            "changed_fields": changed_fields,
            "previous": {field: previous[field] for field in changed_fields},
            "current": {field: current[field] for field in changed_fields},
        },
    )
