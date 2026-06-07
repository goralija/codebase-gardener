from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any


JsonObject = dict[str, Any]
SIGNAL_BUCKETS = (
    "dependency_cycles",
    "hotspots",
    "dead_code_candidates",
    "ownership_risks",
    "test_gaps",
    "dependency_risks",
    "ci_failures",
)


def build_analysis_drift_report(
    *,
    baseline_snapshot: JsonObject | None,
    baseline_entropy: JsonObject | None,
    current_snapshot: JsonObject,
    current_entropy: JsonObject,
    baseline_analysis_id: str = "",
    current_analysis_id: str = "",
    generated_at: datetime | None = None,
) -> JsonObject:
    """Compare two analysis snapshots without exposing raw source content."""

    generated_at = generated_at or datetime.now(UTC)
    baseline_snapshot = baseline_snapshot or {}
    baseline_entropy = baseline_entropy or {}
    no_baseline = not baseline_snapshot

    baseline_signals = _signals_by_key(baseline_snapshot)
    current_signals = _signals_by_key(current_snapshot)

    new_signals = []
    worsened_signals = []
    resolved_signals = []
    unchanged_count = 0

    if no_baseline:
        new_signals = [_signal_summary(signal) for signal in current_signals.values()]
    else:
        for key, signal in current_signals.items():
            baseline_signal = baseline_signals.get(key)
            if baseline_signal is None:
                new_signals.append(_signal_summary(signal))
                continue

            impact_delta = signal["impact"] - baseline_signal["impact"]
            if impact_delta > 0.01:
                worsened = _signal_summary(signal)
                worsened.update(
                    {
                        "baseline_impact": round(baseline_signal["impact"], 2),
                        "current_impact": round(signal["impact"], 2),
                        "impact_delta": round(impact_delta, 2),
                    }
                )
                worsened_signals.append(worsened)
            else:
                unchanged_count += 1

        for key, signal in baseline_signals.items():
            if key not in current_signals:
                resolved_signals.append(_signal_summary(signal))

    new_signals = _sort_signal_summaries(new_signals)
    worsened_signals = _sort_signal_summaries(worsened_signals)
    resolved_signals = _sort_signal_summaries(resolved_signals)

    return {
        "schema_version": "1.0",
        "repository_id": str(current_snapshot.get("repository_id") or ""),
        "baseline_analysis_id": baseline_analysis_id,
        "baseline_commit_sha": str(baseline_snapshot.get("commit_sha") or ""),
        "current_analysis_id": current_analysis_id,
        "current_commit_sha": str(current_snapshot.get("commit_sha") or ""),
        "generated_at": _format_timestamp(generated_at),
        "no_baseline": no_baseline,
        "entropy_delta": _entropy_delta(baseline_entropy, current_entropy),
        "signal_changes": {
            "new": new_signals,
            "worsened": worsened_signals,
            "resolved": resolved_signals,
            "unchanged_count": unchanged_count,
        },
        "hotspot_paths": _hotspot_paths(new_signals, worsened_signals),
        "summary": {
            "new_count": len(new_signals),
            "worsened_count": len(worsened_signals),
            "resolved_count": len(resolved_signals),
            "unchanged_count": unchanged_count,
        },
    }


def _signals_by_key(snapshot: JsonObject) -> dict[tuple[str, str, str, str], JsonObject]:
    indexed: dict[tuple[str, str, str, str], JsonObject] = {}
    signals = snapshot.get("signals") if isinstance(snapshot, dict) else {}
    if not isinstance(signals, dict):
        return indexed

    for bucket in SIGNAL_BUCKETS:
        for signal in signals.get(bucket) or []:
            if not isinstance(signal, dict):
                continue
            summary = _compact_summary(signal)
            path = str(signal.get("path") or "")
            kind = str(signal.get("kind") or _bucket_kind(bucket))
            key = (bucket, path, kind, summary)
            indexed[key] = {
                "bucket": bucket,
                "path": path,
                "kind": kind,
                "summary": summary,
                "impact": _signal_impact(signal),
            }
    return indexed


def _signal_summary(signal: JsonObject) -> JsonObject:
    return {
        "bucket": signal["bucket"],
        "path": signal["path"],
        "kind": signal["kind"],
        "summary": signal["summary"],
        "impact": round(signal["impact"], 2),
    }


def _sort_signal_summaries(signals: list[JsonObject]) -> list[JsonObject]:
    return sorted(
        signals,
        key=lambda signal: (
            -float(signal.get("impact_delta", signal.get("impact", 0))),
            signal.get("bucket", ""),
            signal.get("path", ""),
            signal.get("summary", ""),
        ),
    )


def _hotspot_paths(new_signals: list[JsonObject], worsened_signals: list[JsonObject]) -> list[JsonObject]:
    by_path: dict[str, JsonObject] = defaultdict(
        lambda: {"path": "", "change_count": 0, "impact_delta": 0.0, "reasons": []}
    )
    for signal in [*new_signals, *worsened_signals]:
        path = str(signal.get("path") or "(repository)")
        entry = by_path[path]
        entry["path"] = path
        entry["change_count"] += 1
        entry["impact_delta"] += float(signal.get("impact_delta", signal.get("impact", 0)))
        summary = str(signal.get("summary") or "")
        if summary and summary not in entry["reasons"]:
            entry["reasons"].append(summary)

    ranked = []
    for entry in by_path.values():
        ranked.append(
            {
                "path": entry["path"],
                "change_count": entry["change_count"],
                "impact_delta": round(entry["impact_delta"], 2),
                "reasons": entry["reasons"][:3],
            }
        )
    return sorted(
        ranked,
        key=lambda entry: (-entry["impact_delta"], -entry["change_count"], entry["path"]),
    )


def _entropy_delta(baseline_entropy: JsonObject, current_entropy: JsonObject) -> JsonObject:
    baseline_score = _score(baseline_entropy)
    current_score = _score(current_entropy)
    component_names = sorted(
        set(baseline_score.get("components", {})) | set(current_score.get("components", {}))
    )
    components = {
        name: round(
            float(current_score.get("components", {}).get(name, 0))
            - float(baseline_score.get("components", {}).get(name, 0)),
            2,
        )
        for name in component_names
    }
    return {
        "overall": round(
            float(current_score.get("overall", 0)) - float(baseline_score.get("overall", 0)),
            2,
        ),
        "components": components,
    }


def _score(entropy: JsonObject) -> JsonObject:
    score = entropy.get("score") if isinstance(entropy, dict) else {}
    return score if isinstance(score, dict) else {}


def _compact_summary(signal: JsonObject) -> str:
    summary = str(signal.get("summary") or signal.get("name") or signal.get("reason") or "")
    return " ".join(summary.split())[:240]


def _bucket_kind(bucket: str) -> str:
    return bucket[:-1] if bucket.endswith("s") else bucket


def _signal_impact(signal: JsonObject) -> float:
    for field in ("impact", "score", "risk_score", "severity_score"):
        value = signal.get(field)
        if isinstance(value, int | float):
            return float(value)

    severity = str(signal.get("severity") or "").lower()
    if severity in {"critical", "blocking"}:
        return 5.0
    if severity == "high":
        return 4.0
    if severity == "medium":
        return 2.0
    if severity == "low":
        return 1.0

    numeric_total = 0.0
    for field in ("churn", "complexity", "count"):
        value = signal.get(field)
        if isinstance(value, int | float):
            numeric_total += float(value)
    return numeric_total or 1.0


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
