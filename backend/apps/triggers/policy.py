"""Permission policy for session triggers (E04-T02)."""

from __future__ import annotations

from apps.accounts.models import Membership
from apps.repositories.models import ManagedRepository
<<<<<<< HEAD
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
=======
from apps.triggers.registry import (
    ACTOR_REQUIRED_KINDS,
    FIRST_SCAN,
    MANUAL,
    MANUAL_TRIGGER_ROLES,
)
>>>>>>> 6a20e42 (feat(triggers): gate sessions on user-selected triggers (frontend TODO))


class TriggerNotPermittedError(Exception):
    code = "trigger_not_permitted"


# Trigger kinds that are always on regardless of user selection: manual (the
# user explicitly clicked it) and the onboarding first scan.
ALWAYS_ENABLED_TRIGGER_KINDS = frozenset({MANUAL, FIRST_SCAN})


def trigger_enabled_for_repository(repository: ManagedRepository, kind: str) -> bool:
    """Whether an automated trigger kind is enabled for this repository.

    The user chooses which automated triggers (push, n_commits, risky_module,
    pr_opened, ci_failure, schedule) author code-fix PRs for each repository.
    Manual and first-scan are always enabled.

    TODO(frontend): Build the per-repository "Automation triggers" settings UI
    where the user selects which triggers are enabled, calling a new API
    endpoint to persist the selection
    (e.g. GET/PUT /api/v1/repositories/<id>/triggers).
    TODO(backend): Persist the selection (e.g. a RepositoryTriggerSetting model
    or a field on ManagedRepository) and back this function with it. Until that
    store exists, all triggers are treated as enabled so current behavior is
    unchanged.
    """
    if kind in ALWAYS_ENABLED_TRIGGER_KINDS:
        return True
    # TODO(backend): replace with the user-selected enabled-triggers lookup.
    return True


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
