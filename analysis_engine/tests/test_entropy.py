from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from gardener_analysis import EntropyThresholds, build_entropy_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "fixtures" / "schemas" / "entropy_report.schema.json"
CONTRACTS = PROJECT_ROOT / "fixtures" / "contracts"


def _validate(report: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)


def _snapshot(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "analysis_snapshot_id": "snap_test",
        "repository_id": "repo_test",
        "commit_sha": "deadbeefcafe0001",
        "created_at": "2026-06-06T00:00:00Z",
        "logical_systems": [],
        "signals": {
            "dependency_cycles": [],
            "hotspots": [],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        },
        "constitution_id": "constitution_test",
    }
    base.update(overrides)
    return base


def _constitution(open_questions=None, completeness=1.0) -> dict:
    return {
        "schema_version": "1.0",
        "repository_id": "repo_test",
        "commit_sha": "deadbeefcafe0001",
        "completeness_score": completeness,
        "protected_modules": [],
        "never_touch": [],
        "allowed_fixes": {"autonomous": [], "assisted": [], "advisory": []},
        "architecture_boundaries": [],
        "ignored_paths": [],
        "open_questions": open_questions or [],
    }


def test_contract_fixture_inputs_produce_schema_valid_report():
    snapshot = json.loads((CONTRACTS / "analysis_snapshot.json").read_text())
    constitution = json.loads((CONTRACTS / "repository_constitution.json").read_text())

    report = build_entropy_report(snapshot, constitution)

    _validate(report)
    assert report["schema_version"] == "1.0"
    assert report["repository_id"] == snapshot["repository_id"]
    assert report["analysis_snapshot_id"] == snapshot["analysis_snapshot_id"]


def test_component_weights_cap_each_contribution():
    # Saturate every bucket; weighted contribution must respect the weight cap.
    busy = {bucket: [{"path": f"p{i}.py"} for i in range(20)] for bucket in (
        "dependency_cycles",
        "hotspots",
        "dead_code_candidates",
        "ownership_risks",
        "test_gaps",
        "dependency_risks",
        "ci_failures",
    )}
    report = build_entropy_report(_snapshot(signals=busy), _constitution())
    components = report["score"]["components"]

    assert components["architecture"] <= 25.0
    assert components["maintainability"] <= 25.0
    assert components["knowledge"] <= 15.0
    assert components["testing"] <= 15.0
    assert components["dependency"] <= 10.0
    assert components["operational"] <= 10.0
    assert report["score"]["overall"] <= 100.0


def test_architecture_signals_only_raise_architecture_component():
    snapshot = _snapshot(
        signals={
            "dependency_cycles": [{"path": "a.py"}, {"path": "b.py"}],
            "hotspots": [],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        }
    )
    components = build_entropy_report(snapshot, _constitution())["score"]["components"]

    assert components["architecture"] > 0
    assert components["maintainability"] == 0
    assert components["testing"] == 0


def test_empty_signals_are_healthy_with_low_confidence_forecast():
    report = build_entropy_report(_snapshot(), _constitution())

    assert report["score"]["overall"] == 0.0
    assert report["score"]["classification"] == "healthy"
    assert report["forecast"]["confidence"] == 0.5
    assert 0.0 <= report["forecast"]["predicted_overall"] <= 100.0
    assert report["forecast"]["horizon_days"] == 90


def test_thresholds_drive_classification():
    snapshot = _snapshot(
        signals={
            "dependency_cycles": [],
            "hotspots": [{"path": "x.py"}],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        }
    )
    # maintainability raw 25 * 0.25 weight => overall 6.25 -> 6.2/6.3.
    lenient = build_entropy_report(snapshot, _constitution())
    strict = build_entropy_report(
        snapshot, _constitution(), thresholds=EntropyThresholds(healthy_max=1.0, warning_max=5.0)
    )

    assert lenient["score"]["classification"] == "healthy"
    assert strict["score"]["classification"] == "critical"


def test_blocking_constitution_question_forces_no_autonomy():
    blocking = [{"question_id": "q_001", "severity": "blocking", "question": "?", "evidence": []}]
    report = build_entropy_report(_snapshot(), _constitution(open_questions=blocking))

    assert report["score"]["classification"] == "no_autonomy"


def test_missing_constitution_raises_knowledge_entropy():
    full = build_entropy_report(_snapshot(), _constitution(completeness=1.0))
    empty = build_entropy_report(_snapshot(), _constitution(completeness=0.0))

    assert empty["score"]["components"]["knowledge"] > full["score"]["components"]["knowledge"]


def test_logical_system_scopes_attribute_signals_by_path():
    snapshot = _snapshot(
        logical_systems=[
            {"logical_system_id": "sys_api", "name": "API", "paths": ["apps/api/**"]},
            {"logical_system_id": "sys_web", "name": "Web", "paths": ["apps/web/**"]},
        ],
        signals={
            "dependency_cycles": [],
            "hotspots": [
                {"path": "apps/api/models.py"},
                {"path": "apps/api/views.py"},
            ],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        },
    )
    report = build_entropy_report(snapshot, _constitution())
    systems = {s["scope_id"]: s for s in report["scopes"] if s["scope_type"] == "logical_system"}

    assert systems["sys_api"]["overall"] > 0
    assert systems["sys_web"]["overall"] == 0


def test_module_and_file_scopes_present_and_ranked():
    snapshot = _snapshot(
        signals={
            "dependency_cycles": [],
            "hotspots": [
                {"path": "apps/api/models.py"},
                {"path": "apps/api/models.py"},
                {"path": "apps/web/view.py"},
            ],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        }
    )
    report = build_entropy_report(snapshot, _constitution())

    files = [s for s in report["scopes"] if s["scope_type"] == "file"]
    modules = [s for s in report["scopes"] if s["scope_type"] == "module"]
    assert files and modules
    # Worst file (2 signals) ranks first.
    assert files[0]["scope_id"] == "apps/api/models.py"
    assert files[0]["overall"] >= files[-1]["overall"]


def test_top_contributors_sorted_by_impact_desc():
    snapshot = _snapshot(
        signals={
            "dependency_cycles": [],
            "hotspots": [
                {"path": "a.py", "summary": "small", "score": 2.0},
                {"path": "b.py", "summary": "big", "score": 40.0},
            ],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        }
    )
    contributors = build_entropy_report(snapshot, _constitution())["top_contributors"]

    impacts = [c["impact"] for c in contributors]
    assert impacts == sorted(impacts, reverse=True)
    assert contributors[0]["summary"] == "big"


def test_forecast_trend_degrades_without_history():
    forecast = build_entropy_report(_snapshot(), _constitution())["forecast"]

    trend = forecast["trend"]
    assert trend["direction"] == "unknown"
    assert trend["basis"] == "single_snapshot"
    assert trend["history_points"] == 0


def test_score_explanation_names_dominant_component():
    snapshot = _snapshot(
        signals={
            "dependency_cycles": [],
            "hotspots": [{"path": "a.py"}, {"path": "b.py"}],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        }
    )
    explanation = build_entropy_report(snapshot, _constitution())["score"]["explanation"]

    assert "maintainability" in explanation.lower()


def test_no_autonomy_explanation_references_source_truth():
    blocking = [{"question_id": "q_001", "severity": "blocking", "question": "?", "evidence": []}]
    explanation = build_entropy_report(
        _snapshot(), _constitution(open_questions=blocking)
    )["score"]["explanation"]

    assert "no-autonomy" in explanation.lower()
    assert "constitution" in explanation.lower() or "source-truth" in explanation.lower()


def test_component_explanations_cover_all_components():
    snapshot = _snapshot(
        signals={
            "dependency_cycles": [],
            "hotspots": [{"path": "a.py"}],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        }
    )
    report = build_entropy_report(snapshot, _constitution())
    explanations = report["score"]["component_explanations"]

    assert set(explanations) == {
        "architecture",
        "maintainability",
        "knowledge",
        "testing",
        "dependency",
        "operational",
    }
    assert "no signals" in explanations["architecture"].lower()
    assert "signal" in explanations["maintainability"].lower()


def test_incomplete_constitution_component_explanation_mentions_source_truth():
    explanation = build_entropy_report(_snapshot(), _constitution(completeness=0.0))[
        "score"
    ]["component_explanations"]["knowledge"]

    assert "source truth" in explanation.lower()


def test_every_scope_has_nonempty_explanation():
    snapshot = _snapshot(
        logical_systems=[
            {"logical_system_id": "sys_api", "name": "API", "paths": ["apps/api/**"]}
        ],
        signals={
            "dependency_cycles": [],
            "hotspots": [{"path": "apps/api/models.py"}],
            "dead_code_candidates": [],
            "ownership_risks": [],
            "test_gaps": [],
            "dependency_risks": [],
            "ci_failures": [],
        },
    )
    report = build_entropy_report(snapshot, _constitution())

    assert report["scopes"]
    for scope in report["scopes"]:
        assert scope["explanation"].strip()
        assert scope["classification"] in scope["explanation"]


def test_additions_keep_report_schema_valid():
    snapshot = json.loads((CONTRACTS / "analysis_snapshot.json").read_text())
    constitution = json.loads((CONTRACTS / "repository_constitution.json").read_text())

    report = build_entropy_report(snapshot, constitution)
    _validate(report)
    assert report["forecast"]["trend"]["direction"] == "unknown"
    assert report["score"]["explanation"]


def test_build_is_deterministic():
    snapshot = json.loads((CONTRACTS / "analysis_snapshot.json").read_text())
    constitution = json.loads((CONTRACTS / "repository_constitution.json").read_text())

    assert build_entropy_report(snapshot, constitution) == build_entropy_report(
        snapshot, constitution
    )
