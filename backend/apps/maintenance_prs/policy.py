from __future__ import annotations

from datetime import timedelta
import os
from typing import Any

CONFIDENCE_THRESHOLD_ENV = "GARDENER_CONFIDENCE_THRESHOLD"
PRODUCT_DEFAULT_CONFIDENCE_THRESHOLD = 0.85


def configured_confidence_threshold(default: float = PRODUCT_DEFAULT_CONFIDENCE_THRESHOLD) -> float:
    raw = os.getenv(CONFIDENCE_THRESHOLD_ENV)
    if raw is None:
        return default
    try:
        threshold = float(raw)
    except ValueError:
        return default
    if threshold > 1:
        threshold = threshold / 100
    return max(0.0, min(threshold, 1.0))


DEFAULT_CONFIDENCE_THRESHOLD = configured_confidence_threshold()
DEAD_CODE_CONFIDENCE_THRESHOLD = 0.95
STALE_RUNNING_TIMEOUT = timedelta(minutes=30)


def confidence_threshold_for_opportunity(
    opportunity: dict[str, Any],
    constitution: dict[str, Any],
) -> float:
    # All categories honor the configured threshold (GARDENER_CONFIDENCE_THRESHOLD
    # / constitution risk_policies). dead_code no longer has a special floor.
    return _constitution_confidence_threshold(constitution)


def _constitution_confidence_threshold(constitution: dict[str, Any]) -> float:
    risk_policies = constitution.get("risk_policies")
    if not isinstance(risk_policies, dict):
        return DEFAULT_CONFIDENCE_THRESHOLD

    for key in (
        "confidence_threshold",
        "minimum_confidence",
        "pr_confidence_threshold",
        "autonomous_pr_confidence_threshold",
    ):
        value = risk_policies.get(key)
        if value is not None:
            return _stricter_threshold(value)

    return DEFAULT_CONFIDENCE_THRESHOLD


def _stricter_threshold(value: Any) -> float:
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CONFIDENCE_THRESHOLD
    if threshold > 1:
        threshold = threshold / 100
    return max(DEFAULT_CONFIDENCE_THRESHOLD, min(threshold, 1.0))
