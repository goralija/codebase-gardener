from __future__ import annotations

# Rates represent estimated review + cognitive-load hours per file touched per category.
# Source: conservative internal estimates; not derived from entropy signals.
# dead_code: high removal risk review cost; complexity: refactor review overhead;
# dependency_patch: version bump + changelog + test review; test_gap: test authoring;
# docs: low-risk prose update. Default covers uncategorized work.
HOURS_PER_FILE: dict[str, float] = {
    "dead_code": 3.0,
    "complexity": 2.0,
    "dependency_patch": 1.5,
    "test_gap": 1.0,
    "docs": 0.5,
}
DEFAULT_HOURS_PER_FILE = 1.0
# Proxy threshold: opportunities with entropy delta below this are flagged as
# high-entropy-delta paths. Not equivalent to hotspot signals (central modules
# with rising churn) defined in docs/17-entropy-signal-catalog.md.
ENTROPY_HOTSPOT_THRESHOLD = -1.0


def estimate_roi(group: list[dict], *, blocked: bool = False) -> str:
    if blocked:
        return "No ROI estimate: plan is blocked pending policy review."
    hours_low, hours_high = _hours_saved_range(group)
    high_delta_paths = _high_entropy_delta_count(group)
    assumptions = _build_assumptions(group)

    parts: list[str] = []
    if hours_high > 0:
        parts.append(f"Estimated {hours_low:.1f}–{hours_high:.1f} engineering hours saved.")
    if high_delta_paths > 0:
        parts.append(f"{high_delta_paths} high-entropy-delta path(s) addressed.")
    parts.append(f"Assumptions: {assumptions}")
    parts.append("Estimates are conservative and indicative only.")
    return " ".join(parts)


def _hours_saved_range(group: list[dict]) -> tuple[float, float]:
    total_high = 0.0
    for opportunity in group:
        confidence = float(opportunity.get("confidence") or 0.0)
        paths = opportunity.get("affected_paths") or []
        category = opportunity.get("category", "")
        rate = HOURS_PER_FILE.get(category, DEFAULT_HOURS_PER_FILE)
        base = rate * len(paths) * confidence
        total_high += base
    return total_high * 0.5, total_high


def _high_entropy_delta_count(group: list[dict]) -> int:
    count = 0
    for opportunity in group:
        delta = opportunity.get("expected_entropy_delta")
        if delta is not None and float(delta) < ENTROPY_HOTSPOT_THRESHOLD:
            count += 1
    return count


def _build_assumptions(group: list[dict]) -> str:
    parts: list[str] = []
    seen_categories: set[str] = set()
    for opportunity in group:
        category = opportunity.get("category", "")
        if category and category not in seen_categories:
            rate = HOURS_PER_FILE.get(category, DEFAULT_HOURS_PER_FILE)
            parts.append(f"{rate:.1f} hrs/file for {category}")
            seen_categories.add(category)
    confidences = [
        f"{float(o.get('confidence') or 0.0):.2f}"
        for o in group
        if o.get("confidence") is not None
    ]
    if confidences:
        parts.append(f"confidence {', '.join(confidences)}")
    parts.append("conservative scale 0.5–1.0×")
    return "; ".join(parts) + "."
