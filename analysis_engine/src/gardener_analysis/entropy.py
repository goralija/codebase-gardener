from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonObject = dict[str, Any]

# Component weights from docs/17-entropy-signal-catalog.md.
COMPONENT_WEIGHTS: dict[str, float] = {
    "architecture": 0.25,
    "maintainability": 0.25,
    "knowledge": 0.15,
    "testing": 0.15,
    "dependency": 0.10,
    "operational": 0.10,
}

# Snapshot signal bucket -> entropy component.
_SIGNAL_COMPONENTS: dict[str, str] = {
    "dependency_cycles": "architecture",
    "hotspots": "maintainability",
    "dead_code_candidates": "maintainability",
    "ownership_risks": "knowledge",
    "test_gaps": "testing",
    "dependency_risks": "dependency",
    "ci_failures": "operational",
}

# Numeric fields that, when present on a signal, express its impact.
_IMPACT_FIELDS = ("impact", "health_impact", "score", "churn", "complexity")

_DEFAULT_IMPACT = 5.0
_PER_SIGNAL_RAW = 25.0  # each signal adds this much raw entropy (0-100, saturating).
_MAX_RAW = 100.0


@dataclass(frozen=True)
class EntropyThresholds:
    """Classification cut-points (0-100). Higher score = more degradation.

    Defaults are sensible starting values; callers may override per repository
    (intended to later be sourced from the repository constitution / rules).
    """

    healthy_max: float = 30.0
    warning_max: float = 60.0


def build_entropy_report(
    snapshot: JsonObject,
    constitution: JsonObject,
    entropy_report_id: str | None = None,
    thresholds: EntropyThresholds | None = None,
    forecast_horizon_days: int = 90,
    top_n: int = 10,
) -> JsonObject:
    thresholds = thresholds or EntropyThresholds()
    commit_sha = str(snapshot.get("commit_sha", ""))
    signals = snapshot.get("signals", {}) or {}

    no_autonomy = _has_blocking_questions(constitution)

    components, contributions, overall = _score(signals, constitution)
    classification = (
        "no_autonomy" if no_autonomy else _classify(overall, thresholds)
    )
    counts = _component_counts(signals)

    scopes = _scopes(
        snapshot.get("logical_systems", []) or [],
        signals,
        constitution,
        thresholds,
        top_n,
    )
    top_contributors = _top_contributors(signals, top_n)
    forecast = _forecast(overall, contributions, forecast_horizon_days)

    return {
        "schema_version": "1.0",
        "entropy_report_id": entropy_report_id or f"entropy_{commit_sha[:12]}",
        "repository_id": str(snapshot.get("repository_id", "")),
        "analysis_snapshot_id": str(snapshot.get("analysis_snapshot_id", "")),
        "commit_sha": commit_sha,
        "score": {
            "overall": overall,
            "classification": classification,
            "components": contributions,
            "explanation": _explain_score(
                overall, classification, contributions, no_autonomy
            ),
            "component_explanations": {
                component: _explain_component(
                    component, contributions[component], counts[component]
                )
                for component in COMPONENT_WEIGHTS
            },
        },
        "scopes": scopes,
        "top_contributors": top_contributors,
        "forecast": forecast,
    }


def _component_raw(signals: JsonObject, constitution: JsonObject | None) -> dict[str, float]:
    raw = {component: 0.0 for component in COMPONENT_WEIGHTS}
    for bucket, component in _SIGNAL_COMPONENTS.items():
        count = len(_as_list(signals.get(bucket)))
        raw[component] = min(_MAX_RAW, raw[component] + count * _PER_SIGNAL_RAW)

    # Knowledge entropy also rises with an incomplete / missing constitution.
    if constitution is not None:
        completeness = _as_float(constitution.get("completeness_score"), default=1.0)
        penalty = (1.0 - _clamp(completeness, 0.0, 1.0)) * 50.0
        raw["knowledge"] = min(_MAX_RAW, raw["knowledge"] + penalty)

    return raw


def _score(
    signals: JsonObject, constitution: JsonObject | None
) -> tuple[dict[str, float], dict[str, float], float]:
    raw = _component_raw(signals, constitution)
    contributions = {
        component: round(raw[component] * weight, 1)
        for component, weight in COMPONENT_WEIGHTS.items()
    }
    overall = round(sum(contributions.values()), 1)
    return raw, contributions, overall


def _component_counts(signals: JsonObject) -> dict[str, int]:
    counts = {component: 0 for component in COMPONENT_WEIGHTS}
    for bucket, component in _SIGNAL_COMPONENTS.items():
        counts[component] += len(_as_list(signals.get(bucket)))
    return counts


def _explain_score(
    overall: float,
    classification: str,
    contributions: dict[str, float],
    no_autonomy: bool,
) -> str:
    if no_autonomy:
        return (
            "No-autonomy: a blocking source-truth / constitution question prevents "
            "safe autonomous PRs regardless of the numeric score."
        )
    drivers = [name for name, value in
               sorted(contributions.items(), key=lambda kv: (-kv[1], kv[0])) if value > 0][:2]
    label = classification.capitalize()
    if not drivers:
        return f"{label}: no significant entropy signals (overall {overall})."
    joined = " and ".join(drivers)
    return f"{label}: {joined} entropy {'are' if len(drivers) > 1 else 'is'} the main driver(s); overall {overall}."


def _explain_component(component: str, contribution: float, count: int) -> str:
    cap = round(COMPONENT_WEIGHTS[component] * 100)
    if contribution <= 0:
        return f"{component.capitalize()}: no signals (0/{cap})."
    if count == 0:
        # Knowledge can rise from an incomplete constitution rather than signals.
        return (
            f"{component.capitalize()}: {contribution}/{cap} from incomplete source truth."
        )
    plural = "s" if count != 1 else ""
    return f"{component.capitalize()}: {contribution}/{cap} from {count} signal{plural}."


def _classify(overall: float, thresholds: EntropyThresholds) -> str:
    if overall < thresholds.healthy_max:
        return "healthy"
    if overall < thresholds.warning_max:
        return "warning"
    return "critical"


def _scopes(
    logical_systems: list[JsonObject],
    signals: JsonObject,
    constitution: JsonObject,
    thresholds: EntropyThresholds,
    top_n: int,
) -> list[JsonObject]:
    scopes: list[JsonObject] = []

    # Logical-system level.
    for system in logical_systems:
        if not isinstance(system, dict):
            continue
        globs = system.get("paths", []) or []
        subset = _filter_signals(signals, globs)
        _, _, overall = _score(subset, constitution=None)
        classification = _classify(overall, thresholds)
        name = system.get("name", "")
        scopes.append(
            {
                "scope_type": "logical_system",
                "scope_id": system.get("logical_system_id", ""),
                "name": name,
                "overall": overall,
                "classification": classification,
                "explanation": _explain_scope(
                    "logical_system", name, overall, classification
                ),
            }
        )

    # Module + file level: count signals per path / per parent directory.
    file_counts: dict[str, int] = {}
    module_counts: dict[str, int] = {}
    for path in _signal_paths(signals):
        file_counts[path] = file_counts.get(path, 0) + 1
        module = _module_of(path)
        module_counts[module] = module_counts.get(module, 0) + 1

    scopes.extend(
        _ranked_scopes("module", module_counts, thresholds, top_n)
    )
    scopes.extend(
        _ranked_scopes("file", file_counts, thresholds, top_n)
    )
    return scopes


def _ranked_scopes(
    scope_type: str,
    counts: dict[str, int],
    thresholds: EntropyThresholds,
    top_n: int,
) -> list[JsonObject]:
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    scopes: list[JsonObject] = []
    for scope_id, count in ranked:
        overall = round(min(_MAX_RAW, count * _PER_SIGNAL_RAW), 1)
        classification = _classify(overall, thresholds)
        scopes.append(
            {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "name": scope_id,
                "overall": overall,
                "classification": classification,
                "explanation": _explain_scope(
                    scope_type, scope_id, overall, classification, count
                ),
            }
        )
    return scopes


def _explain_scope(
    scope_type: str,
    name: str,
    overall: float,
    classification: str,
    count: int | None = None,
) -> str:
    label = scope_type.replace("_", " ")
    base = f"{name or label}: {label} entropy {overall} ({classification})"
    if count is not None:
        plural = "s" if count != 1 else ""
        return f"{base} from {count} signal{plural}."
    return f"{base}."


def _top_contributors(signals: JsonObject, top_n: int) -> list[JsonObject]:
    contributors: list[JsonObject] = []
    for bucket, component in _SIGNAL_COMPONENTS.items():
        for signal in _as_list(signals.get(bucket)):
            if not isinstance(signal, dict):
                continue
            contributors.append(
                {
                    "kind": signal.get("kind", bucket),
                    "summary": signal.get("summary", f"{component} entropy signal."),
                    "impact": _impact(signal),
                    "evidence": _as_list(signal.get("evidence")),
                }
            )
    contributors.sort(key=lambda item: (-item["impact"], item["kind"], item["summary"]))
    return contributors[:top_n]


def _forecast(
    overall: float, components: dict[str, float], horizon_days: int
) -> JsonObject:
    # Single snapshot => no trend history. Degrade to a low-confidence,
    # current-state projection per docs/17 forecast rules.
    dominant = max(components, key=lambda key: components[key]) if components else None
    drift = 5.0 if overall >= 60.0 else 0.0
    predicted = round(_clamp(overall + drift, 0.0, 100.0), 1)
    if dominant and components[dominant] > 0:
        summary = (
            f"{dominant.title()} entropy is the largest contributor; "
            "projection is low-confidence without historical trend data."
        )
    else:
        summary = "No significant entropy signals; stable outlook (low confidence, no trend history)."
    return {
        "horizon_days": horizon_days,
        "predicted_overall": predicted,
        "confidence": 0.5,
        "summary": summary,
        # No stored history yet => direction unknown. Forward-compatible for when
        # multiple snapshots over time enable rising/falling/stable detection.
        "trend": {
            "direction": "unknown",
            "basis": "single_snapshot",
            "history_points": 0,
        },
    }


# --- helpers ---------------------------------------------------------------


def _has_blocking_questions(constitution: JsonObject) -> bool:
    for question in _as_list(constitution.get("open_questions")):
        if isinstance(question, dict) and question.get("severity") == "blocking":
            return True
    return False


def _filter_signals(signals: JsonObject, globs: list[str]) -> JsonObject:
    filtered: JsonObject = {}
    for bucket in _SIGNAL_COMPONENTS:
        items = [
            signal
            for signal in _as_list(signals.get(bucket))
            if isinstance(signal, dict) and _matches(signal.get("path"), globs)
        ]
        filtered[bucket] = items
    return filtered


def _signal_paths(signals: JsonObject) -> list[str]:
    paths: list[str] = []
    for bucket in _SIGNAL_COMPONENTS:
        for signal in _as_list(signals.get(bucket)):
            if isinstance(signal, dict):
                path = signal.get("path")
                if isinstance(path, str) and path:
                    paths.append(path)
    return paths


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
    for field in _IMPACT_FIELDS:
        value = signal.get(field)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return _DEFAULT_IMPACT


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any, default: float) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
