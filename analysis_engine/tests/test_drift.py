from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from gardener_analysis import build_analysis_drift_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "fixtures" / "schemas" / "analysis_drift_report.schema.json"


def _validate(report: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)


def _snapshot(commit_sha: str, signals: dict) -> dict:
    return {
        "schema_version": "1.0",
        "analysis_snapshot_id": f"snap_{commit_sha}",
        "repository_id": "repo_test",
        "commit_sha": commit_sha,
        "created_at": "2026-06-07T00:00:00Z",
        "logical_systems": [],
        "signals": {
            "dependency_cycles": signals.get("dependency_cycles", []),
            "hotspots": signals.get("hotspots", []),
            "dead_code_candidates": signals.get("dead_code_candidates", []),
            "ownership_risks": signals.get("ownership_risks", []),
            "test_gaps": signals.get("test_gaps", []),
            "dependency_risks": signals.get("dependency_risks", []),
            "ci_failures": signals.get("ci_failures", []),
        },
        "constitution_id": "constitution_test",
    }


def _entropy(overall: float, **components: float) -> dict:
    return {
        "schema_version": "1.0",
        "entropy_report_id": "entropy_test",
        "repository_id": "repo_test",
        "analysis_snapshot_id": "snap_test",
        "commit_sha": "commit",
        "score": {"overall": overall, "classification": "warning", "components": components},
        "scopes": [],
        "top_contributors": [],
        "forecast": {"horizon_days": 90, "predicted_overall": overall, "confidence": 0.5, "summary": ""},
    }


def test_drift_report_identifies_signal_changes_and_hotspots():
    baseline = _snapshot(
        "base123",
        {
            "hotspots": [
                {"path": "src/a.py", "summary": "A is busy", "score": 2.0},
                {"path": "src/stable.py", "summary": "Stable issue", "score": 1.0},
            ],
            "test_gaps": [{"path": "tests/old.py", "summary": "Old gap", "impact": 3.0}],
        },
    )
    current = _snapshot(
        "cur456",
        {
            "hotspots": [
                {"path": "src/a.py", "summary": "A is busy", "score": 7.0},
                {"path": "src/stable.py", "summary": "Stable issue", "score": 1.0},
                {"path": "src/new.py", "summary": "New hotspot", "score": 4.0},
            ],
            "dependency_risks": [
                {"path": "package.json", "summary": "Lockfile drift", "impact": 2.0}
            ],
        },
    )

    report = build_analysis_drift_report(
        baseline_snapshot=baseline,
        baseline_entropy=_entropy(10.0, architecture=3.0, testing=2.0),
        current_snapshot=current,
        current_entropy=_entropy(17.5, architecture=5.5, testing=1.0),
        baseline_analysis_id="analysis_base",
        current_analysis_id="analysis_current",
        generated_at=datetime(2026, 6, 7, tzinfo=UTC),
    )

    _validate(report)
    assert report["baseline_commit_sha"] == "base123"
    assert report["current_commit_sha"] == "cur456"
    assert report["entropy_delta"] == {
        "overall": 7.5,
        "components": {"architecture": 2.5, "testing": -1.0},
    }
    assert [item["path"] for item in report["signal_changes"]["new"]] == [
        "src/new.py",
        "package.json",
    ]
    assert report["signal_changes"]["worsened"][0]["path"] == "src/a.py"
    assert report["signal_changes"]["worsened"][0]["impact_delta"] == 5.0
    assert report["signal_changes"]["resolved"][0]["path"] == "tests/old.py"
    assert report["signal_changes"]["unchanged_count"] == 1
    assert report["hotspot_paths"][0]["path"] == "src/a.py"


def test_no_baseline_report_is_current_only_and_schema_valid():
    current = _snapshot(
        "cur456",
        {"test_gaps": [{"path": "tests/new.py", "summary": "Missing regression", "impact": 2.0}]},
    )

    report = build_analysis_drift_report(
        baseline_snapshot=None,
        baseline_entropy=None,
        current_snapshot=current,
        current_entropy=_entropy(4.0, testing=4.0),
        current_analysis_id="analysis_current",
        generated_at=datetime(2026, 6, 7, tzinfo=UTC),
    )

    _validate(report)
    assert report["no_baseline"] is True
    assert report["baseline_analysis_id"] == ""
    assert report["signal_changes"]["new"][0]["path"] == "tests/new.py"
    assert report["signal_changes"]["resolved"] == []
