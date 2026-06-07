"""Permission policy for session triggers (E04-T02)."""

from __future__ import annotations

from apps.accounts.models import Membership
from apps.repositories.models import ManagedRepository
from apps.triggers.registry import ACTOR_REQUIRED_KINDS, MANUAL_TRIGGER_ROLES
from apps.triggers import registry
from apps.triggers.models import RepositoryAutomationPolicy


CONSERVATIVE_AUTONOMY_PR_BLOCK_REASON = (
    "Repository autonomy mode is Conservative; sessions report recommendations "
    "without PR creation."
)
ASSISTED_AUTONOMY_PR_BLOCK_REASON = (
    "Repository autonomy mode is Assisted; autonomous PR execution is paused."
)

TRIGGER_POLICY_FIELDS = {
    registry.MANUAL: "manual_trigger_enabled",
    registry.SCHEDULE: "scheduled_trigger_enabled",
    registry.N_COMMITS: "commit_trigger_enabled",
    registry.RISKY_MODULE: "risky_module_trigger_enabled",
    registry.PR_OPENED: "pr_opened_trigger_enabled",
    registry.CI_FAILURE: "ci_failure_trigger_enabled",
}


class TriggerNotPermittedError(Exception):
    code = "trigger_not_permitted"


def ensure_trigger_permitted(
    *,
    repository: ManagedRepository,
    kind: str,
    actor=None,
) -> None:
    """Raise ``TriggerNotPermittedError`` if the trigger is not allowed.

    Every trigger requires an active managed repository. Actor-initiated kinds
    (manual) additionally require the actor to hold an active membership with a
    privileged role in the repository's organization.
    """

    if not repository.is_active:
        raise TriggerNotPermittedError("Repository is not active.")

    policy = None
    policy_field = TRIGGER_POLICY_FIELDS.get(kind)
    if policy_field is not None:
        policy = RepositoryAutomationPolicy.get_or_create_for_repository(repository)
        if not getattr(policy, policy_field):
            raise TriggerNotPermittedError(f"{kind} trigger is disabled for this repository.")

    if kind not in ACTOR_REQUIRED_KINDS:
        return

    if actor is None:
        raise TriggerNotPermittedError(f"{kind} trigger requires an actor.")

    has_role = (
        Membership.objects.active()
        .filter(
            user=actor,
            organization_id=repository.organization_id,
            role__in=MANUAL_TRIGGER_ROLES,
        )
        .exists()
    )
    if not has_role:
        raise TriggerNotPermittedError(
            "Actor lacks permission to trigger sessions for this repository."
        )


def autonomous_pr_execution_block_reason(repository: ManagedRepository) -> str | None:
    policy = RepositoryAutomationPolicy.get_or_create_for_repository(repository)
    if policy.autonomy_mode == RepositoryAutomationPolicy.AutonomyMode.AUTONOMOUS:
        return None
    if policy.autonomy_mode == RepositoryAutomationPolicy.AutonomyMode.ASSISTED:
        return ASSISTED_AUTONOMY_PR_BLOCK_REASON
    return CONSERVATIVE_AUTONOMY_PR_BLOCK_REASON
