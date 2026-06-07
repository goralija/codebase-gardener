import pytest

from apps.maintenance_prs.manual_plans import (
    ManualPlanPayloadError,
    build_manual_plan_payload,
    normalize_manual_plan_payload,
)
from apps.maintenance_prs.policy import DEFAULT_CONFIDENCE_THRESHOLD


def test_build_manual_plan_payload_applies_defaults_and_overrides():
    payload = build_manual_plan_payload(
        changed_paths=["core/views.py", "core/views.py", "core/admin.py"],
        pr_body_sections={"goal": "Reduce complexity."},
    )

    assert payload["title"] == "Manual AI maintenance"
    assert payload["category"] == "complexity_reduction"
    assert payload["confidence"] == 0.95
    assert payload["confidence_threshold"] == DEFAULT_CONFIDENCE_THRESHOLD
    assert payload["changed_paths"] == ["core/views.py", "core/admin.py"]
    assert payload["pr_body_sections"]["goal"] == "Reduce complexity."
    assert payload["pr_body_sections"]["verification"]
    assert payload["required_checks"] == []
    assert payload["approve"] is True


def test_normalize_manual_plan_payload_validates_shape():
    with pytest.raises(ManualPlanPayloadError, match="changed_paths"):
        normalize_manual_plan_payload({"changed_paths": []})

    with pytest.raises(ManualPlanPayloadError, match="must be numbers"):
        normalize_manual_plan_payload(
            {"changed_paths": ["core/views.py"], "confidence": "high"}
        )
