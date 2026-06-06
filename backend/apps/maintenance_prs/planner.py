from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Iterable

from django.db import transaction

from apps.billing.services import (
    AUTONOMOUS_PR_ADD_ON_DISABLED_REASON,
    autonomous_pr_add_on_enabled,
)
from apps.maintenance_prs.models import MaintenancePRPlan, MaintenancePRPlanOpportunity
from apps.maintenance_prs.policy import (
    DEAD_CODE_CONFIDENCE_THRESHOLD,
    DEFAULT_CONFIDENCE_THRESHOLD,
    confidence_threshold_for_opportunity,
)
from apps.maintenance_prs.roi import estimate_roi
from apps.triggers.policy import autonomous_pr_execution_block_reason


CONFIDENCE_THRESHOLD = DEFAULT_CONFIDENCE_THRESHOLD
GROUP_SIZE_LIMIT = 3
CATEGORY_ALIASES = {
    "dead_code_removal": "dead_code",
    "dead-code-removal": "dead_code",
    "dead code removal": "dead_code",
}
# Categories whose prior PRs were reverted demand stronger evidence than the
# ordinary autonomous threshold before Gardener tries the same category again.
REVERTED_CONFIDENCE_THRESHOLD = 0.97


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
    automation_decision = _automation_decision(repository)
    billing_decision = _billing_decision(repository)

    with transaction.atomic():
        for group in groups:
            decision = _group_decision(group, constitution, profile)
            forced_reason = forced_block_reasons.get(group[0]["maintenance_opportunity_id"])
            if forced_reason:
                decision = PolicyDecision(True, forced_reason)
            if automation_decision.blocked and not decision.blocked:
                decision = automation_decision
            if billing_decision.blocked and not decision.blocked:
                decision = billing_decision
            branch_name = _unique_branch_name(_base_branch_name(group), used_branch_names)
            used_branch_names.add(branch_name)
            plan = MaintenancePRPlan.objects.create(
                repository=repository,
                gardening_session_id=gardening_session_id,
                branch_name=branch_name,
                title=_plan_title(group),
                category=_plan_category(group),
                risk_tier=_risk_tier(group),
                confidence=min(float(item["confidence"]) for item in group),
                confidence_threshold=_group_confidence_threshold(group, constitution, profile),
                changed_paths=_unique_values(
                    path for item in group for path in item.get("affected_paths", [])
                ),
                pr_body_sections=_pr_body_sections(group, decision, constitution, profile),
                required_checks=_unique_values(
                    check for item in group for check in item.get("required_checks", [])
                ),
                blocked=decision.blocked,
                block_reason=decision.reason,
            )
            for opportunity in group:
                MaintenancePRPlanOpportunity.objects.create(
                    plan=plan,
                    maintenance_opportunity_id=opportunity["maintenance_opportunity_id"],
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

    blocked_by = opportunity.get("blocked_by") or []
    if blocked_by:
        return PolicyDecision(True, "Opportunity is blocked by prerequisite work.")

    confidence = float(opportunity.get("confidence", 0))
    category = opportunity.get("category", "")
    threshold = _effective_threshold(opportunity, constitution, profile)
    if category == "dead_code" and confidence < DEAD_CODE_CONFIDENCE_THRESHOLD:
        return PolicyDecision(
            True,
            f"Dead-code removal requires confidence >= {DEAD_CODE_CONFIDENCE_THRESHOLD:.2f}.",
        )
    if confidence < threshold:
        return PolicyDecision(True, f"Confidence below {threshold:.2f} PR creation threshold.")

    allowed_fixes = _canonical_allowed_fixes(constitution.get("allowed_fixes", {}))
    if category in allowed_fixes.get("advisory", []):
        return PolicyDecision(True, "Opportunity category is advisory-only.")
    if category in allowed_fixes.get("assisted", []):
        return PolicyDecision(True, "Opportunity category requires assisted draft PR handling.")
    if category not in allowed_fixes.get("autonomous", []):
        return PolicyDecision(True, "Opportunity category is not allowed for autonomous PRs.")

    if opportunity.get("risk_tier") != "tier_1_autonomous":
        return PolicyDecision(True, "Risk tier requires assisted or advisory handling.")

    protected_reason = _protected_path_reason(opportunity.get("affected_paths", []), constitution)
    if protected_reason:
        return PolicyDecision(True, protected_reason)

    # Learned profile signals are advisory and never override the constitution:
    # every constitution check above runs first, so this only adds a soft block
    # for categories reviewers have previously rejected.
    if category and category in set(profile.get("rejected_categories") or []):
        return PolicyDecision(
            True,
            "Category previously rejected by reviewers; deferred by learned profile.",
        )

    return PolicyDecision(False)


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


def _billing_decision(repository) -> PolicyDecision:
    if autonomous_pr_add_on_enabled(repository.organization):
        return PolicyDecision(False)
    return PolicyDecision(True, AUTONOMOUS_PR_ADD_ON_DISABLED_REASON)


def _automation_decision(repository) -> PolicyDecision:
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


def _protected_path_reason(paths: list[str], constitution: dict) -> str | None:
    for path in paths:
        for rule in constitution.get("never_touch", []):
            if fnmatch(path, rule.get("path", "")):
                return f"Path {path} matches never-touch rule: {rule.get('reason', 'no reason given')}"
        for module in constitution.get("protected_modules", []):
            for pattern in module.get("paths", []):
                if fnmatch(path, pattern):
                    return (
                        f"Path {path} matches protected module "
                        f"{module.get('name', 'unknown')}: {module.get('reason', 'no reason given')}"
                    )
    return None


def _base_branch_name(group: list[dict]) -> str:
    category = group[0].get("category", "maintenance")
    source = group[0].get("title", category)
    return f"gardener/{_slug(category)}-{_slug(source)}"[:240].rstrip("-")


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


def _plan_category(group: list[dict]) -> str:
    return str(group[0].get("category") or "")


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
    checks = _unique_values(check for item in group for check in item.get("required_checks", []))
    confidence = min(float(item.get("confidence", 0)) for item in group)
    threshold = _group_confidence_threshold(group, constitution, profile)
    changed_paths = _unique_values(path for item in group for path in item.get("affected_paths", []))
    categories = _unique_values(item.get("category", "unknown") for item in group)
    confidence_reasons = (
        f"Minimum opportunity confidence {confidence:.2f}; threshold {threshold:.2f}; "
        f"{'blocked by policy' if decision.blocked else 'meets autonomous PR threshold'}."
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
        verification = f"Blocked: {decision.reason}. {verification}"

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
