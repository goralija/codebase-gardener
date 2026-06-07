from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from apps.maintenance_prs.models import MaintenancePRPlan
from apps.maintenance_prs.policy import DEFAULT_CONFIDENCE_THRESHOLD

DEFAULT_MANUAL_TITLE = "Manual AI maintenance"
DEFAULT_MANUAL_CATEGORY = "complexity_reduction"
DEFAULT_MANUAL_RISK_TIER = "tier_1_autonomous"
DEFAULT_MANUAL_CONFIDENCE = 0.95
DEFAULT_MANUAL_CONFIDENCE_THRESHOLD = DEFAULT_CONFIDENCE_THRESHOLD
DEFAULT_MANUAL_REQUIRED_CHECKS: list[str] = []
DEFAULT_MANUAL_PR_BODY_SECTIONS = {
    "goal": "Manual maintenance run.",
    "evidence": "Manual trigger payload.",
    "entropy_impact": "Manual verification.",
    "verification": "Review; do not merge without human approval.",
}
MAX_MANUAL_CHANGED_PATHS = 20


class ManualPlanPayloadError(ValueError):
    pass


def build_manual_plan_payload(
    *,
    changed_paths: Iterable[str],
    title: str = DEFAULT_MANUAL_TITLE,
    category: str = DEFAULT_MANUAL_CATEGORY,
    risk_tier: str = DEFAULT_MANUAL_RISK_TIER,
    confidence: float = DEFAULT_MANUAL_CONFIDENCE,
    confidence_threshold: float = DEFAULT_MANUAL_CONFIDENCE_THRESHOLD,
    pr_body_sections: dict[str, Any] | None = None,
    required_checks: list[str] | None = None,
    approve: bool = True,
) -> dict[str, Any]:
    paths = _clean_changed_paths(changed_paths)
    sections = dict(DEFAULT_MANUAL_PR_BODY_SECTIONS)
    sections.update(pr_body_sections or {})
    return {
        "title": str(title or DEFAULT_MANUAL_TITLE),
        "category": str(category or DEFAULT_MANUAL_CATEGORY),
        "risk_tier": str(risk_tier or DEFAULT_MANUAL_RISK_TIER),
        "confidence": float(confidence),
        "confidence_threshold": float(confidence_threshold),
        "changed_paths": paths,
        "pr_body_sections": sections,
        "required_checks": required_checks or list(DEFAULT_MANUAL_REQUIRED_CHECKS),
        "approve": bool(approve),
    }


def normalize_manual_plan_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManualPlanPayloadError("manual_plan must be an object.")

    changed_paths = raw.get("changed_paths")
    if not isinstance(changed_paths, list):
        raise ManualPlanPayloadError(
            "manual_plan.changed_paths must be a non-empty list."
        )

    try:
        confidence = float(raw.get("confidence", DEFAULT_MANUAL_CONFIDENCE))
        confidence_threshold = float(
            raw.get("confidence_threshold", DEFAULT_MANUAL_CONFIDENCE_THRESHOLD)
        )
    except (TypeError, ValueError) as exc:
        raise ManualPlanPayloadError(
            "manual_plan.confidence and confidence_threshold must be numbers."
        ) from exc

    pr_body_sections = raw.get("pr_body_sections") or {}
    if not isinstance(pr_body_sections, dict):
        raise ManualPlanPayloadError("manual_plan.pr_body_sections must be an object.")

    required_checks = raw.get("required_checks") or list(DEFAULT_MANUAL_REQUIRED_CHECKS)
    if not isinstance(required_checks, list):
        raise ManualPlanPayloadError("manual_plan.required_checks must be a list.")

    return build_manual_plan_payload(
        title=str(raw.get("title") or DEFAULT_MANUAL_TITLE),
        category=str(raw.get("category") or DEFAULT_MANUAL_CATEGORY),
        risk_tier=str(raw.get("risk_tier") or DEFAULT_MANUAL_RISK_TIER),
        confidence=confidence,
        confidence_threshold=confidence_threshold,
        changed_paths=changed_paths,
        pr_body_sections=pr_body_sections,
        required_checks=required_checks,
        approve=bool(raw.get("approve", True)),
    )


def create_manual_session_pr_plan(session, payload: dict[str, Any]) -> MaintenancePRPlan:
    normalized = normalize_manual_plan_payload(payload)
    branch_name = manual_plan_branch_name(session)
    existing = MaintenancePRPlan.objects.for_session(str(session.id)).filter(
        branch_name=branch_name
    ).first()
    if existing is not None:
        return existing

    return MaintenancePRPlan.objects.create(
        repository=session.repository,
        gardening_session_id=str(session.id),
        branch_name=branch_name,
        title=normalized["title"],
        category=normalized["category"],
        risk_tier=normalized["risk_tier"],
        confidence=normalized["confidence"],
        confidence_threshold=normalized["confidence_threshold"],
        changed_paths=normalized["changed_paths"],
        pr_body_sections=normalized["pr_body_sections"],
        required_checks=normalized["required_checks"],
        blocked=False,
        approval_status=(
            MaintenancePRPlan.ApprovalStatus.APPROVED
            if normalized["approve"]
            else MaintenancePRPlan.ApprovalStatus.PENDING
        ),
    )


def manual_plan_branch_name(session) -> str:
    return f"gardener/manual-ai-{str(session.id)[:8]}"


def _clean_changed_paths(changed_paths: Iterable[str]) -> list[str]:
    paths: list[str] = []
    for path in changed_paths:
        if not isinstance(path, str) or not path.strip():
            raise ManualPlanPayloadError(
                "manual_plan.changed_paths must contain only non-empty strings."
            )
        cleaned = path.strip()
        if cleaned not in paths:
            paths.append(cleaned)
        if len(paths) >= MAX_MANUAL_CHANGED_PATHS:
            break
    if not paths:
        raise ManualPlanPayloadError(
            "manual_plan.changed_paths must be a non-empty list."
        )
    return paths
