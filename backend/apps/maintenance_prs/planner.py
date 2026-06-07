from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Iterable

from django.db import transaction

from apps.maintenance_prs.models import MaintenancePRPlan, MaintenancePRPlanOpportunity
from apps.maintenance_prs.policy import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    confidence_threshold_for_opportunity,
)
from apps.maintenance_prs.roi import estimate_roi
from apps.triggers.models import RepositoryAutomationPolicy
from apps.triggers.policy import autonomous_pr_execution_block_reason


CONFIDENCE_THRESHOLD = DEFAULT_CONFIDENCE_THRESHOLD
GROUP_SIZE_LIMIT = 3
logger = logging.getLogger(__name__)
CATEGORY_ALIASES = {
    "dead_code_removal": "dead_code",
    "dead-code-removal": "dead_code",
    "dead code removal": "dead_code",
}
# Categories whose prior PRs were reverted demand stronger evidence than the
# ordinary autonomous threshold before Gardener tries the same category again.
REVERTED_CONFIDENCE_THRESHOLD = 0.97
POLICY_BLOCK_MARKERS = {"below_confidence_threshold"}
POLICY_BLOCK_PREFIXES = ("protected_module:", "never_touch:")
LEGACY_GENERATED_REQUIRED_CHECKS = {
    "dependency_audit",
    "python -m pytest",
    "pytest",
    "uv run python -m pytest",
    "uv run pytest",
}


@dataclass(frozen=True)
class PolicyDecision:
    blocked: bool
    reason: str | None = None


def plan_maintenance_prs(
    *,
    repository,
    gardening_session_id: str,
    opportunities: Iterable[dict],
    constitution: dict,
    profile: dict | None = None,
) -> list[MaintenancePRPlan]:
    profile = profile or {}
    accepted_categories = set(profile.get("accepted_categories") or [])
    ordered_opportunities = sorted(
        opportunities,
        key=lambda item: (
            # Accepted categories rank ahead of equally-confident peers.
            0 if item.get("category", "") in accepted_categories else 1,
            -float(item.get("confidence", 0)),
            item.get("category", ""),
            item.get("maintenance_opportunity_id", ""),
        ),
    )
    existing_opportunity_ids = set(
        MaintenancePRPlanOpportunity.objects.filter(
            repository=repository,
            gardening_session_id=gardening_session_id,
        ).values_list("maintenance_opportunity_id", flat=True)
    )

    groups: list[list[dict]] = []
    forced_block_reasons: dict[str, str] = {}
    for opportunity in ordered_opportunities:
        opportunity_id = opportunity["maintenance_opportunity_id"]
        if opportunity_id in existing_opportunity_ids:
            continue

        decision = evaluate_policy(opportunity, constitution, profile)
        if decision.blocked:
            groups.append([opportunity])
            continue
        if _conflicts_with_unblocked_groups(
            groups, opportunity, constitution, profile, forced_block_reasons
        ):
            forced_block_reasons[opportunity_id] = (
                "Opportunity conflicts with another selected PR plan in this session."
            )
            groups.append([opportunity])
            continue

        for group in groups:
            if _group_is_blocked(group, constitution, profile, forced_block_reasons):
                continue
            if _compatible(group, opportunity):
                group.append(opportunity)
                break
        else:
            groups.append([opportunity])

    plans: list[MaintenancePRPlan] = []
    used_branch_names = set(
        MaintenancePRPlan.objects.filter(
            repository=repository,
            gardening_session_id=gardening_session_id,
        ).values_list("branch_name", flat=True)
    )
    with transaction.atomic():
        for group in groups:
            decision = _group_decision(group, constitution, profile)
            forced_reason = forced_block_reasons.get(group[0]["maintenance_opportunity_id"])
            if forced_reason:
                decision = PolicyDecision(True, forced_reason)
            automation_decision = _automation_decision(repository, group)
            if automation_decision.blocked and not decision.blocked:
                decision = automation_decision
            branch_name = _unique_branch_name(
                _base_branch_name(group, gardening_session_id), used_branch_names
            )
            used_branch_names.add(branch_name)
            plan = MaintenancePRPlan.objects.create(
                repository=repository,
                gardening_session_id=gardening_session_id,
                branch_name=branch_name,
                title=_plan_title(group),
                category=_plan_category(group),
                risk_tier=_plan_risk_tier(group, constitution),
                confidence=min(float(item["confidence"]) for item in group),
                confidence_threshold=_group_confidence_threshold(group, constitution, profile),
                changed_paths=_unique_values(
                    path for item in group for path in item.get("affected_paths", [])
                ),
                pr_body_sections=_pr_body_sections(group, decision, constitution, profile),
                required_checks=_group_required_checks(group),
                blocked=decision.blocked,
                block_reason=decision.reason,
            )
            for opportunity in group:
                MaintenancePRPlanOpportunity.objects.create(
                    plan=plan,
                    maintenance_opportunity_id=opportunity["maintenance_opportunity_id"],
                )
            logger.info(
                "maintenance_pr_plan.blocked"
                if plan.blocked
                else "maintenance_pr_plan.created",
                extra=_plan_log_extra(plan, group),
            )
            plans.append(plan)

    return plans


def serialize_maintenance_pr_plan(plan: MaintenancePRPlan) -> dict:
    return plan.to_contract()


def evaluate_policy(
    opportunity: dict,
    constitution: dict,
    profile: dict | None = None,
) -> PolicyDecision:
    profile = profile or {}
    if _has_blocking_open_questions(constitution):
        return PolicyDecision(True, "Repository constitution has unresolved open questions.")

    confidence = float(opportunity.get("confidence", 0))
    category = opportunity.get("category", "")
    threshold = _effective_threshold(opportunity, constitution, profile)
    prerequisite_blockers = _prerequisite_blockers(opportunity)
    if prerequisite_blockers:
        return PolicyDecision(
            True,
            f"Opportunity is blocked by prerequisite work: {', '.join(prerequisite_blockers)}.",
        )

    never_touch_reason = _never_touch_reason(opportunity.get("affected_paths", []), constitution)
    if never_touch_reason:
        return PolicyDecision(True, never_touch_reason)

    # Protected modules no longer hard-block. Such plans are forced to the
    # advisory tier (draft PR + risk label) in plan creation so reviewers gate
    # them instead of policy. never-touch paths stay a hard block above.
    if confidence < threshold:
        return PolicyDecision(True, f"Confidence below {threshold:.2f} PR creation threshold.")

    allowed_fixes = _canonical_allowed_fixes(constitution.get("allowed_fixes", {}))
    if category in allowed_fixes.get("advisory", []):
        return PolicyDecision(False)
    if category in allowed_fixes.get("assisted", []):
        return PolicyDecision(False)
    if category not in allowed_fixes.get("autonomous", []):
        return PolicyDecision(True, "Opportunity category is not allowed for PR creation.")

    if opportunity.get("risk_tier") not in {
        "tier_1_autonomous",
        "tier_2_assisted",
        "tier_3_advisory",
    }:
        return PolicyDecision(True, "Risk tier is not supported for PR creation.")

    # Learned profile signals are advisory and never override the constitution:
    # every constitution check above runs first, so this only adds a soft block
    # for categories reviewers have previously rejected.
    if category and category in set(profile.get("rejected_categories") or []):
        return PolicyDecision(
            True,
            "Category previously rejected by reviewers; deferred by learned profile.",
        )

    return PolicyDecision(False)


def _prerequisite_blockers(opportunity: dict) -> list[str]:
    blockers: list[str] = []
    for blocker in opportunity.get("blocked_by") or []:
        value = str(blocker).strip()
        if not value:
            continue
        if value in POLICY_BLOCK_MARKERS:
            continue
        if any(value.startswith(prefix) for prefix in POLICY_BLOCK_PREFIXES):
            continue
        blockers.append(value)
    return blockers


def _group_decision(
    group: list[dict],
    constitution: dict,
    profile: dict | None = None,
) -> PolicyDecision:
    decisions = [evaluate_policy(opportunity, constitution, profile) for opportunity in group]
    for decision in decisions:
        if decision.blocked:
            return decision
    return PolicyDecision(False)


def _automation_decision(repository, group: list[dict]) -> PolicyDecision:
    if _risk_tier(group) == "tier_2_assisted":
        policy = RepositoryAutomationPolicy.get_or_create_for_repository(repository)
        if policy.autonomy_mode in {
            RepositoryAutomationPolicy.AutonomyMode.ASSISTED,
            RepositoryAutomationPolicy.AutonomyMode.AUTONOMOUS,
        }:
            return PolicyDecision(False)
        reason = autonomous_pr_execution_block_reason(repository)
        if reason:
            return PolicyDecision(True, reason)
        return PolicyDecision(False)

    reason = autonomous_pr_execution_block_reason(repository)
    if reason:
        return PolicyDecision(True, reason)
    return PolicyDecision(False)


def _effective_threshold(
    opportunity: dict,
    constitution: dict,
    profile: dict | None = None,
) -> float:
    profile = profile or {}
    threshold = confidence_threshold_for_opportunity(opportunity, constitution)
    category = opportunity.get("category", "")
    if category and category in set(profile.get("reverted_categories") or []):
        threshold = max(threshold, REVERTED_CONFIDENCE_THRESHOLD)
    return threshold


def _canonical_allowed_fixes(allowed_fixes: dict) -> dict[str, list[str]]:
    return {
        group: _canonical_categories(allowed_fixes.get(group, []))
        for group in ("autonomous", "assisted", "advisory")
    }


def _canonical_categories(values) -> list[str]:
    categories: list[str] = []
    for value in values if isinstance(values, list) else []:
        category = CATEGORY_ALIASES.get(str(value), str(value))
        if category not in categories:
            categories.append(category)
    return categories


def _has_blocking_open_questions(constitution: dict) -> bool:
    for question in constitution.get("open_questions", []):
        if question.get("severity", "blocking") == "blocking":
            return True
    return False


def _compatible(group: list[dict], opportunity: dict) -> bool:
    if len(group) >= GROUP_SIZE_LIMIT:
        return False
    first = group[0]
    if first.get("category") != opportunity.get("category"):
        return False
    if first.get("risk_tier") != opportunity.get("risk_tier"):
        return False

    existing_paths = {path for item in group for path in item.get("affected_paths", [])}
    new_paths = set(opportunity.get("affected_paths", []))
    return existing_paths.isdisjoint(new_paths)


def _conflicts_with_unblocked_groups(
    groups: list[list[dict]],
    opportunity: dict,
    constitution: dict,
    profile: dict | None = None,
    forced_block_reasons: dict[str, str] | None = None,
) -> bool:
    new_paths = set(opportunity.get("affected_paths", []))
    if not new_paths:
        return False
    for group in groups:
        if _group_is_blocked(group, constitution, profile, forced_block_reasons):
            continue
        existing_paths = {path for item in group for path in item.get("affected_paths", [])}
        if not existing_paths.isdisjoint(new_paths):
            return True
    return False


def _group_is_blocked(
    group: list[dict],
    constitution: dict,
    profile: dict | None = None,
    forced_block_reasons: dict[str, str] | None = None,
) -> bool:
    """A group is unusable as a merge target / conflict source when it is blocked.

    Force-blocked groups (path-conflict blocks recorded in ``forced_block_reasons``)
    are invisible to :func:`_group_decision`, which only re-derives policy blocks.
    Treating both kinds as blocked stops a later opportunity from being merged into,
    or falsely conflicting with, a group that will never produce a PR. Forced groups
    are always single-item, so ``group[0]`` identifies them reliably.
    """

    if forced_block_reasons and group[0]["maintenance_opportunity_id"] in forced_block_reasons:
        return True
    return _group_decision(group, constitution, profile).blocked


def _never_touch_reason(paths: list[str], constitution: dict) -> str | None:
    for path in paths:
        for rule in constitution.get("never_touch", []):
            if fnmatch(path, rule.get("path", "")):
                return f"Path {path} matches never-touch rule: {rule.get('reason', 'no reason given')}"
    return None


def _protected_module_reason(paths: list[str], constitution: dict) -> str | None:
    for path in paths:
        for module in constitution.get("protected_modules", []):
            for pattern in module.get("paths", []):
                if fnmatch(path, pattern):
                    return (
                        f"Path {path} matches protected module "
                        f"{module.get('name', 'unknown')}: {module.get('reason', 'no reason given')}"
                    )
    return None


def _base_branch_name(group: list[dict], gardening_session_id: str = "") -> str:
    category = group[0].get("category", "maintenance")
    source = group[0].get("title", category)
    # Scope the branch to this session so re-runs of the same category+title get a
    # fresh branch instead of colliding with a stale branch left by a prior run.
    suffix = _session_branch_suffix(gardening_session_id)
    base = f"gardener/{_slug(category)}-{_slug(source)}"
    if suffix:
        base = f"{base[:240 - len(suffix) - 1]}-{suffix}"
    return base[:240].rstrip("-")


def _session_branch_suffix(gardening_session_id: str) -> str:
    digest = re.sub(r"[^a-z0-9]", "", str(gardening_session_id).lower())
    return digest[-8:] if digest else ""


def _unique_branch_name(base_branch_name: str, used_branch_names: set[str]) -> str:
    if base_branch_name not in used_branch_names:
        return base_branch_name

    counter = 2
    while True:
        suffix = f"-{counter}"
        candidate = f"{base_branch_name[:255 - len(suffix)]}{suffix}"
        if candidate not in used_branch_names:
            return candidate
        counter += 1


def _plan_title(group: list[dict]) -> str:
    if len(group) == 1:
        return group[0]["title"]
    return f"Plan {len(group)} {group[0]['category']} maintenance opportunities"


def _risk_tier(group: list[dict]) -> str:
    return group[0].get("risk_tier", "unknown")


def _plan_risk_tier(group: list[dict], constitution: dict) -> str:
    """Force protected-module groups to the advisory tier so they ship as draft
    PRs gated by review + risk label instead of being hard-blocked."""
    paths = [path for item in group for path in item.get("affected_paths", [])]
    if _protected_module_reason(paths, constitution):
        return "tier_3_advisory"
    return _risk_tier(group)


def _plan_category(group: list[dict]) -> str:
    return str(group[0].get("category") or "")


def _group_required_checks(group: list[dict]) -> list[str]:
    return _unique_values(
        check
        for item in group
        for check in _sanitized_required_checks(item.get("required_checks", []))
    )


def _sanitized_required_checks(value) -> list[str]:
    checks: list[str] = []
    for check in value if isinstance(value, list) else []:
        if not isinstance(check, str):
            continue
        normalized = check.strip()
        if not normalized or normalized.lower() in LEGACY_GENERATED_REQUIRED_CHECKS:
            continue
        checks.append(normalized)
    return checks


def _plan_log_extra(plan: MaintenancePRPlan, group: list[dict]) -> dict:
    opportunity_ids = [
        str(item.get("maintenance_opportunity_id"))
        for item in group
        if item.get("maintenance_opportunity_id")
    ]
    return {
        "organization_id": str(plan.repository.organization_id),
        "repository_id": str(plan.repository_id),
        "gardening_session_id": plan.gardening_session_id,
        "maintenance_pr_plan_id": str(plan.id),
        "maintenance_opportunity_ids": opportunity_ids,
        "maintenance_opportunity_count": len(opportunity_ids),
        "category": plan.category,
        "risk_tier": plan.risk_tier,
        "confidence": plan.confidence,
        "confidence_threshold": plan.confidence_threshold,
        "blocked": plan.blocked,
        "block_reason": plan.block_reason or "",
        "changed_path_count": len(plan.changed_paths or []),
        "required_check_count": len(plan.required_checks or []),
    }


def _pr_body_sections(
    group: list[dict],
    decision: PolicyDecision,
    constitution: dict,
    profile: dict | None = None,
) -> dict:
    evidence = []
    for opportunity in group:
        for item in opportunity.get("evidence", []):
            summary = item.get("summary")
            path = item.get("path")
            if summary and path:
                evidence.append(f"{path}: {summary}")
            elif summary:
                evidence.append(summary)

    entropy_delta = sum(float(item.get("expected_entropy_delta", 0)) for item in group)
    checks = _group_required_checks(group)
    confidence = min(float(item.get("confidence", 0)) for item in group)
    threshold = _group_confidence_threshold(group, constitution, profile)
    changed_paths = _unique_values(path for item in group for path in item.get("affected_paths", []))
    categories = _unique_values(item.get("category", "unknown") for item in group)
    if decision.blocked:
        threshold_outcome = "blocked by policy"
    elif _risk_tier(group) in {"tier_2_assisted", "tier_3_advisory"}:
        threshold_outcome = "eligible for review-required PR"
    else:
        threshold_outcome = "meets autonomous PR threshold"
    confidence_reasons = (
        f"Minimum opportunity confidence {confidence:.2f}; threshold {threshold:.2f}; "
        f"{threshold_outcome}."
    )
    constitution_rules = (
        f"Categories checked against constitution allowed fixes: {', '.join(categories)}. "
        f"Changed paths checked against protected modules and never-touch paths: {', '.join(changed_paths)}."
    )

    verification = (
        f"Required checks: {', '.join(checks) if checks else 'none configured'}. "
        f"Risk tier: {_risk_tier(group)}. {confidence_reasons} "
        f"Changed paths: {', '.join(changed_paths)}. "
        "Rollback: revert the focused PR branch if checks or review fail."
    )
    if decision.blocked:
        verification = f"Blocked: {_sentence(decision.reason)} {verification}"

    return {
        "goal": " | ".join(item.get("summary", item["title"]) for item in group),
        "evidence": (
            f"{' | '.join(evidence) if evidence else 'No source evidence supplied.'} "
            f"{constitution_rules}"
        ),
        "entropy_impact": f"Expected {entropy_delta:.1f} entropy delta across {len(changed_paths)} path(s).",
        "verification": verification,
        "roi_impact": estimate_roi(group, blocked=decision.blocked),
    }


def _sentence(value: str | None) -> str:
    text = (value or "Blocked by PR planning policy.").strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _unique_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _group_confidence_threshold(
    group: list[dict],
    constitution: dict,
    profile: dict | None = None,
) -> float:
    return max(_effective_threshold(item, constitution, profile) for item in group)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "maintenance"
