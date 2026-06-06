from __future__ import annotations

from typing import Any


JsonObject = dict[str, Any]

# Snapshot signal bucket -> opportunity category. `hotspots` is split by path
# (docs vs complexity) inside _signal_category.
_BUCKET_CATEGORY: dict[str, str] = {
    "dead_code_candidates": "dead_code",
    "test_gaps": "tests",
    "dependency_risks": "dependency_patch",
    "dependency_cycles": "layer_violation_repair",
}

# Default tier per category when the constitution does not list it (docs/09).
_DEFAULT_TIER: dict[str, str] = {
    "docs": "tier_1_autonomous",
    "lint_format": "tier_1_autonomous",
    "generated_refresh": "tier_1_autonomous",
    "dependency_patch": "tier_1_autonomous",
    "dead_code": "tier_1_autonomous",
    "tests": "tier_2_assisted",
    "refactoring": "tier_2_assisted",
    "complexity_reduction": "tier_2_assisted",
    "layer_violation_repair": "tier_2_assisted",
    "module_extraction": "tier_2_assisted",
}

_TIER_BY_ALLOWED_GROUP = {
    "autonomous": "tier_1_autonomous",
    "assisted": "tier_2_assisted",
    "advisory": "tier_3_advisory",
}

_REQUIRED_CHECKS: dict[str, list[str]] = {
    "docs": ["docs_review"],
    "dependency_patch": ["pytest", "dependency_audit"],
    "dead_code": ["pytest"],
    "tests": ["pytest"],
    "complexity_reduction": ["pytest"],
    "layer_violation_repair": ["pytest"],
}

# Per-category base confidence. dead_code uses the signals' own confidence.
_BASE_CONFIDENCE: dict[str, float] = {
    "docs": 0.95,
    "dependency_patch": 0.85,
    "tests": 0.70,
    "complexity_reduction": 0.60,
    "layer_violation_repair": 0.60,
    "dead_code": 0.90,
}

_CONFIDENCE_THRESHOLD = 0.90
_MAX_AFFECTED_PATHS = 20
_MAX_EVIDENCE = 3

# Category -> entropy component, used to size expected_entropy_delta.
_CATEGORY_COMPONENT: dict[str, str] = {
    "docs": "knowledge",
    "tests": "testing",
    "dead_code": "maintainability",
    "complexity_reduction": "maintainability",
    "dependency_patch": "dependency",
    "layer_violation_repair": "architecture",
}


def generate_maintenance_opportunities(
    snapshot: JsonObject,
    entropy: JsonObject,
    constitution: JsonObject,
    top_n: int = 50,
) -> list[JsonObject]:
    repository_id = str(snapshot.get("repository_id", ""))
    analysis_snapshot_id = str(snapshot.get("analysis_snapshot_id", ""))
    signals = snapshot.get("signals", {}) or {}

    ignored = _string_globs(constitution.get("ignored_paths"))
    protected = _protected_globs(constitution.get("protected_modules"))
    never_touch = _never_touch_globs(constitution.get("never_touch"))
    allowed = constitution.get("allowed_fixes", {}) or {}
    components = (entropy.get("score", {}) or {}).get("components", {}) or {}

    # Group signals by (category, module).
    groups: dict[tuple[str, str], list[JsonObject]] = {}
    for bucket, items in signals.items():
        for signal in _as_list(items):
            if not isinstance(signal, dict):
                continue
            path = signal.get("path")
            if isinstance(path, str) and _matches(path, ignored):
                continue
            category = _signal_category(bucket, path)
            if category is None:
                continue
            module = _module_of(path) if isinstance(path, str) and path else "repository"
            groups.setdefault((category, module), []).append(signal)

    # Build one opportunity per group.
    built: list[tuple[float, JsonObject]] = []
    for (category, module), group_signals in groups.items():
        group_impact = sum(_impact(s) for s in group_signals)
        opportunity = _build_opportunity(
            category=category,
            module=module,
            group_signals=group_signals,
            repository_id=repository_id,
            analysis_snapshot_id=analysis_snapshot_id,
            allowed=allowed,
            protected=protected,
            never_touch=never_touch,
            components=components,
            category_group_count=_category_group_count(groups),
        )
        built.append((group_impact, opportunity))

    # Rank by aggregate impact (desc), then stable by id; cap at top_n.
    built.sort(key=lambda item: (-item[0], item[1]["maintenance_opportunity_id"]))
    return [opportunity for _, opportunity in built[:top_n]]


def _build_opportunity(
    *,
    category: str,
    module: str,
    group_signals: list[JsonObject],
    repository_id: str,
    analysis_snapshot_id: str,
    allowed: JsonObject,
    protected: list[tuple[str, str]],
    never_touch: list[str],
    components: JsonObject,
    category_group_count: dict[str, int],
) -> JsonObject:
    affected_paths = sorted(
        {
            str(s.get("path"))
            for s in group_signals
            if isinstance(s.get("path"), str) and s.get("path")
        }
    )[:_MAX_AFFECTED_PATHS]

    blocked_by: list[str] = []
    risk_tier = _risk_tier(category, allowed)

    # Protected / never-touch override -> advisory + blocked reasons.
    for path in affected_paths:
        if _matches(path, never_touch):
            risk_tier = "tier_3_advisory"
            blocked_by.append(f"never_touch:{path}")
        for name, glob in protected:
            if _matches(path, [glob]):
                risk_tier = "tier_3_advisory"
                blocked_by.append(f"protected_module:{name}")
    blocked_by = sorted(set(blocked_by))

    confidence = _confidence(category, group_signals)
    if confidence < _CONFIDENCE_THRESHOLD:
        blocked_by = sorted(set(blocked_by + ["below_confidence_threshold"]))

    entropy_delta = _expected_entropy_delta(
        category, len(group_signals), components, category_group_count
    )

    return {
        "schema_version": "1.0",
        "maintenance_opportunity_id": f"opp_{category}_{_slug(module)}",
        "repository_id": repository_id,
        "analysis_snapshot_id": analysis_snapshot_id,
        "category": category,
        "risk_tier": risk_tier,
        "confidence": round(confidence, 2),
        "title": _title(category, module),
        "summary": _summary(category, module, len(group_signals)),
        "affected_paths": affected_paths,
        "blocked_by": blocked_by,
        "expected_entropy_delta": entropy_delta,
        "required_checks": _REQUIRED_CHECKS.get(category, ["pytest"]),
        "evidence": _evidence(group_signals),
    }


def _signal_category(bucket: str, path: str | None) -> str | None:
    if bucket == "hotspots":
        if isinstance(path, str) and path.lower().endswith(".md"):
            return "docs"
        return "complexity_reduction"
    return _BUCKET_CATEGORY.get(bucket)


def _risk_tier(category: str, allowed: JsonObject) -> str:
    for group, tier in _TIER_BY_ALLOWED_GROUP.items():
        values = allowed.get(group)
        if isinstance(values, list) and category in values:
            return tier
    return _DEFAULT_TIER.get(category, "tier_2_assisted")


def _confidence(category: str, group_signals: list[JsonObject]) -> float:
    if category == "dead_code":
        values = [
            float(s["confidence"])
            for s in group_signals
            if isinstance(s.get("confidence"), int | float)
            and not isinstance(s.get("confidence"), bool)
        ]
        if values:
            return _clamp(min(values), 0.0, 1.0)
    return _clamp(_BASE_CONFIDENCE.get(category, 0.6), 0.0, 1.0)


def _expected_entropy_delta(
    category: str,
    group_size: int,
    components: JsonObject,
    category_group_count: dict[str, int],
) -> float:
    component = _CATEGORY_COMPONENT.get(category)
    contribution = 0.0
    if component is not None:
        value = components.get(component)
        if isinstance(value, int | float) and not isinstance(value, bool):
            contribution = float(value)
    groups_for_category = max(1, category_group_count.get(category, 1))
    # Distribute the component's entropy contribution across its groups; reducing
    # this opportunity is expected to remove (a share of) that entropy.
    share = contribution / groups_for_category
    delta = -round(share, 1)
    if delta == 0.0 and group_size > 0:
        delta = -0.1  # always a small positive reduction when signals exist
    return delta


def _category_group_count(
    groups: dict[tuple[str, str], list[JsonObject]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for category, _module in groups:
        counts[category] = counts.get(category, 0) + 1
    return counts


def _evidence(group_signals: list[JsonObject]) -> list[JsonObject]:
    evidence: list[JsonObject] = []
    for signal in group_signals[:_MAX_EVIDENCE]:
        path = signal.get("path")
        if not isinstance(path, str) or not path:
            continue
        evidence.append(
            {
                "source_type": "file",
                "path": path,
                "summary": str(signal.get("summary") or "Analysis signal."),
            }
        )
    return evidence


def _title(category: str, module: str) -> str:
    label = category.replace("_", " ")
    return f"Address {label} in {module}"


def _summary(category: str, module: str, count: int) -> str:
    label = category.replace("_", " ")
    plural = "s" if count != 1 else ""
    return f"{count} {label} signal{plural} found in {module}."


# --- path / value helpers (kept local to stay module-independent) ----------


def _protected_globs(protected_modules: Any) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for module in _as_list(protected_modules):
        if not isinstance(module, dict):
            continue
        name = str(module.get("name", "module"))
        for path in _as_list(module.get("paths")):
            if isinstance(path, str) and path:
                result.append((name, path))
    return result


def _never_touch_globs(never_touch: Any) -> list[str]:
    result: list[str] = []
    for entry in _as_list(never_touch):
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            result.append(entry["path"])
    return result


def _string_globs(value: Any) -> list[str]:
    return [item for item in _as_list(value) if isinstance(item, str) and item]


def _module_of(path: str) -> str:
    parts = path.split("/")
    if len(parts) <= 1:
        return parts[0]
    return "/".join(parts[:2])


def _matches(path: str | None, globs: list[str]) -> bool:
    if not isinstance(path, str) or not path:
        return False
    for glob in globs:
        if not isinstance(glob, str):
            continue
        base = glob.replace("**", "").rstrip("/*")
        if base == "" or path == base or path.startswith(base + "/") or path.startswith(base):
            return True
    return False


def _impact(signal: JsonObject) -> float:
    for field in ("impact", "health_impact", "score", "churn", "complexity"):
        value = signal.get(field)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return 5.0


def _slug(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
    return slug or "repository"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
