from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.common.models import AuditEvent
from apps.maintenance_prs.models import MaintenancePRPlan
from apps.profiles.models import GardenerProfile

LEARNING_AUDIT_SOURCE = "gardening_worker"


class Outcome:
    """Recognized PR outcomes (doc-09 §Learning rules)."""

    MERGED = "merged"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CLOSED = "closed"
    REVERTED = "reverted"
    EDITED = "edited"
    FAILED = "failed"


VALID_OUTCOMES = frozenset(
    {
        Outcome.MERGED,
        Outcome.ACCEPTED,
        Outcome.REJECTED,
        Outcome.CLOSED,
        Outcome.REVERTED,
        Outcome.EDITED,
        Outcome.FAILED,
    }
)

# outcome -> profile category-list field that gains this plan's category
_CATEGORY_FIELD_BY_OUTCOME = {
    Outcome.MERGED: "accepted_categories",
    Outcome.ACCEPTED: "accepted_categories",
    Outcome.REJECTED: "rejected_categories",
    Outcome.CLOSED: "rejected_categories",
    Outcome.REVERTED: "reverted_categories",
}


class OutcomeLearningError(Exception):
    pass


@dataclass(frozen=True)
class OutcomeResult:
    recorded: bool
    profile_updated: bool
    outcome: str
    maintenance_pr_plan_id: str


def find_plan_for_pull_request(
    *,
    repository,
    pr_number: int | None = None,
    branch_name: str | None = None,
) -> MaintenancePRPlan | None:
    """Locate the gardener plan behind a GitHub PR/branch.

    Matches on the created PR number first, then the plan branch name. Returns
    ``None`` for PRs that Gardener did not author so callers can ignore them.
    """

    plans = MaintenancePRPlan.objects.filter(repository=repository)
    if pr_number is not None:
        plan = plans.filter(created_pr_number=pr_number).order_by("-created_at").first()
        if plan is not None:
            return plan
    if branch_name:
        return plans.filter(branch_name=branch_name).order_by("-created_at").first()
    return None


def record_pr_outcome(
    *,
    plan: MaintenancePRPlan,
    outcome: str,
    source_metadata: dict[str, Any] | None = None,
) -> OutcomeResult:
    """Ingest a PR outcome and update the repository's GardenerProfile.

    Learning only adds soft signals; it never overrides explicit constitution
    rules (doc-16 §Memory rules). Idempotent on ``(plan, outcome)`` so a
    redelivered webhook does not double-append.
    """

    if outcome not in VALID_OUTCOMES:
        raise OutcomeLearningError(f"Unsupported PR outcome: {outcome!r}")

    plan_id = str(plan.id)
    category = (plan.category or "").strip()
    metadata = dict(source_metadata or {})

    with transaction.atomic():
        # get_or_create handles the concurrent-first-webhook race (it retries the
        # get on a unique-violation); the row is then locked for this update.
        GardenerProfile.objects.get_or_create(repository_id=plan.repository_id)
        profile = GardenerProfile.objects.select_for_update().get(
            repository_id=plan.repository_id
        )

        if _already_recorded(profile, plan_id, outcome):
            return OutcomeResult(
                recorded=False,
                profile_updated=False,
                outcome=outcome,
                maintenance_pr_plan_id=plan_id,
            )

        _persist_plan_outcome_state(plan, outcome, metadata)

        signal_fields = _apply_outcome(profile, plan, outcome, category)
        profile.updated_from_pr_outcomes = list(profile.updated_from_pr_outcomes or []) + [
            {
                "maintenance_pr_id": plan_id,
                "outcome": outcome,
                "category": category,
            }
        ]
        profile.save(update_fields=sorted(signal_fields | {"updated_from_pr_outcomes", "updated_at"}))

        _audit(
            plan,
            AuditEvent.EventType.MAINTENANCE_PR_OUTCOME_RECORDED,
            {"outcome": outcome, "category": category, **metadata},
        )
        # Only audit a profile change when a ranking signal (not just the log)
        # actually changed; FAILED is log-only and must not look like a mutation.
        if signal_fields:
            _audit(
                plan,
                AuditEvent.EventType.GARDENER_PROFILE_UPDATED,
                {"outcome": outcome, "category": category, "fields": sorted(signal_fields)},
            )

    return OutcomeResult(
        recorded=True,
        profile_updated=bool(signal_fields),
        outcome=outcome,
        maintenance_pr_plan_id=plan_id,
    )


def _persist_plan_outcome_state(
    plan: MaintenancePRPlan,
    outcome: str,
    metadata: dict[str, Any],
) -> None:
    """Record the merge commit SHA so reverts can be matched precisely later."""

    if outcome != Outcome.MERGED:
        return
    merge_commit_sha = str(metadata.get("merge_commit_sha") or "").strip()
    if merge_commit_sha and plan.merge_commit_sha != merge_commit_sha:
        # Atomic single-row update avoids a read-modify-write race with a
        # concurrent revert webhook and skips full_clean on a partial write.
        MaintenancePRPlan.objects.filter(pk=plan.pk).update(
            merge_commit_sha=merge_commit_sha
        )
        plan.merge_commit_sha = merge_commit_sha


def _already_recorded(profile: GardenerProfile, plan_id: str, outcome: str) -> bool:
    for entry in profile.updated_from_pr_outcomes or []:
        if entry.get("maintenance_pr_id") == plan_id and entry.get("outcome") == outcome:
            return True
    return False


def _apply_outcome(
    profile: GardenerProfile,
    plan: MaintenancePRPlan,
    outcome: str,
    category: str,
) -> set[str]:
    changed: set[str] = set()

    category_field = _CATEGORY_FIELD_BY_OUTCOME.get(outcome)
    if category_field and category:
        if _append_unique(profile, category_field, category):
            changed.add(category_field)

    if outcome == Outcome.REVERTED:
        reason = f"Reverted gardener PR (category={category or 'unknown'})."
        for path in plan.changed_paths or []:
            if _append_protected_pattern(profile, path, reason):
                changed.add("learned_protected_patterns")

    if outcome == Outcome.EDITED:
        note = (
            f"Humans edited gardener PRs for category '{category or 'unknown'}'; "
            "review these changes before autonomous handling."
        )
        if _append_unique(profile, "review_preferences", note):
            changed.add("review_preferences")

    # Outcome.FAILED is a ranking-only signal: it is logged via
    # updated_from_pr_outcomes but mutates no category lists.
    return changed


def _append_unique(profile: GardenerProfile, field: str, value: str) -> bool:
    values = list(getattr(profile, field) or [])
    if value in values:
        return False
    values.append(value)
    setattr(profile, field, values)
    return True


def _append_protected_pattern(profile: GardenerProfile, pattern: str, reason: str) -> bool:
    patterns = list(profile.learned_protected_patterns or [])
    if any(entry.get("pattern") == pattern for entry in patterns):
        return False
    patterns.append({"pattern": pattern, "reason": reason})
    profile.learned_protected_patterns = patterns
    return True


def _audit(plan: MaintenancePRPlan, event_type: str, metadata: dict[str, Any]) -> None:
    repository = plan.repository
    AuditEvent.objects.create(
        organization=repository.organization,
        github_installation=repository.github_installation,
        repository=repository,
        event_type=event_type,
        source=LEARNING_AUDIT_SOURCE,
        metadata={"maintenance_pr_plan_id": str(plan.id), **metadata},
    )
