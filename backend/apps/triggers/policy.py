"""Permission policy for session triggers (E04-T02)."""

from __future__ import annotations

from apps.accounts.models import Membership
from apps.repositories.models import ManagedRepository
from apps.triggers.registry import ACTOR_REQUIRED_KINDS, MANUAL_TRIGGER_ROLES


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
