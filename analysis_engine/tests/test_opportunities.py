from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from gardener_analysis import generate_maintenance_opportunities


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    PROJECT_ROOT / "fixtures" / "schemas" / "maintenance_opportunity.schema.json"
)
CONTRACTS = PROJECT_ROOT / "fixtures" / "contracts"


def _validate(opportunity: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(opportunity)


def _empty_signals() -> dict:
    return {
        "dependency_cycles": [],
        "hotspots": [],
        "dead_code_candidates": [],
        "ownership_risks": [],
        "test_gaps": [],
        "dependency_risks": [],
        "ci_failures": [],
    }


def _snapshot(**signal_overrides) -> dict:
    signals = _empty_signals()
    signals.update(signal_overrides)
    return {
        "schema_version": "1.0",
        "analysis_snapshot_id": "snap_test",
        "repository_id": "repo_test",
        "commit_sha": "abc",
        "created_at": "2026-06-06T00:00:00Z",
        "logical_systems": [],
        "signals": signals,
        "constitution_id": "const_test",
    }


def _entropy(**components) -> dict:
    base = {
        "architecture": 0.0,
        "maintainability": 10.0,
        "knowledge": 5.0,
        "testing": 8.0,
        "dependency": 4.0,
        "operational": 0.0,
    }
    base.update(components)
    return {"score": {"overall": 0.0, "classification": "warning", "components": base}}


def _constitution(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "repository_id": "repo_test",
        "commit_sha": "abc",
        "completeness_score": 1.0,
        "protected_modules": [],
        "never_touch": [],
        "allowed_fixes": {
            "autonomous": ["docs", "dependency_patch", "dead_code"],
            "assisted": ["tests", "complexity_reduction", "layer_violation_repair"],
            "advisory": ["auth", "payments"],
        },
        "architecture_boundaries": [],
        "ignored_paths": [],
        "open_questions": [],
    }
    base.update(overrides)
    return base


def _generate(snapshot, constitution=None, entropy=None, **kw):
    return generate_maintenance_opportunities(
        snapshot, entropy or _entropy(), constitution or _constitution(), **kw
    )


def test_contract_fixtures_produce_schema_valid_opportunities():
    snapshot = json.loads((CONTRACTS / "analysis_snapshot.json").read_text())
    entropy = json.loads((CONTRACTS / "entropy_report.json").read_text())
    constitution = json.loads((CONTRACTS / "repository_constitution.json").read_text())

    opportunities = generate_maintenance_opportunities(snapshot, entropy, constitution)

    for opp in opportunities:
        _validate(opp)
        assert opp["schema_version"] == "1.0"
        assert opp["repository_id"] == snapshot["repository_id"]


def _only(opportunities, category):
    matches = [o for o in opportunities if o["category"] == category]
    assert matches, f"no {category} opportunity in {[o['category'] for o in opportunities]}"
    return matches[0]


def test_docs_case():
    snap = _snapshot(hotspots=[{"path": "docs/guide.md", "summary": "stale"}])
    opp = _only(_generate(snap), "docs")

    _validate(opp)
    assert opp["risk_tier"] == "tier_1_autonomous"
    assert "docs_review" in opp["required_checks"]
    assert opp["expected_entropy_delta"] < 0


def test_dependency_case():
    snap = _snapshot(dependency_risks=[{"path": "pyproject.toml", "summary": "outdated"}])
    opp = _only(_generate(snap), "dependency_patch")

    assert opp["risk_tier"] == "tier_1_autonomous"
    assert opp["required_checks"] == []


def test_confidence_below_autonomous_floor_is_flagged():
    snap = _snapshot(
        dependency_risks=[{"path": "pyproject.toml", "summary": "outdated"}]
    )
    opp = _only(_generate(snap), "dependency_patch")

    assert opp["confidence"] == 0.85
    assert "below_confidence_threshold" not in opp["blocked_by"]


def test_confidence_threshold_override_allows_medium_confidence(monkeypatch):
    monkeypatch.setenv("GARDENER_CONFIDENCE_THRESHOLD", "0.50")
    snap = _snapshot(hotspots=[{"path": "core/service.py", "summary": "complex"}])
    opp = _only(_generate(snap), "complexity_reduction")

    assert opp["confidence"] == 0.6
    assert "below_confidence_threshold" not in opp["blocked_by"]


def test_dead_code_below_autonomous_floor_is_flagged(monkeypatch):
    monkeypatch.delenv("GARDENER_CONFIDENCE_THRESHOLD", raising=False)
    snap = _snapshot(
        dead_code_candidates=[
            {"path": "core/util.py", "confidence": 0.5, "summary": "unused"}
        ]
    )
    opp = _only(_generate(snap), "dead_code")

    assert opp["confidence"] == 0.5
    assert "below_confidence_threshold" in opp["blocked_by"]


def test_dead_code_high_confidence_not_flagged():
    snap = _snapshot(
        dead_code_candidates=[
            {"path": "core/util.py", "confidence": 0.97, "summary": "unused"}
        ]
    )
    opp = _only(_generate(snap), "dead_code")

    assert opp["confidence"] == 0.97
    assert "below_confidence_threshold" not in opp["blocked_by"]


def test_source_code_opportunities_do_not_assume_pytest():
    snap = _snapshot(
        dead_code_candidates=[
            {"path": "src/app.ts", "confidence": 0.97, "summary": "unused"}
        ]
    )
    opp = _only(_generate(snap), "dead_code")

    assert opp["required_checks"] == []


def test_architecture_case():
    snap = _snapshot(dependency_cycles=[{"path": "core/a.py", "summary": "cycle"}])
    opp = _only(_generate(snap), "layer_violation_repair")

    assert opp["risk_tier"] == "tier_2_assisted"


def test_protected_module_forces_advisory_and_blocks():
    snap = _snapshot(
        dead_code_candidates=[
            {"path": "src/auth/tokens.py", "confidence": 0.99, "summary": "unused"}
        ]
    )
    const = _constitution(
        protected_modules=[
            {"name": "auth", "paths": ["src/auth/**"], "reason": "security"}
        ]
    )
    opp = _only(_generate(snap, const), "dead_code")

    assert opp["risk_tier"] == "tier_3_advisory"
    assert any(b.startswith("protected_module:auth") for b in opp["blocked_by"])


def test_never_touch_forces_advisory_and_blocks():
    snap = _snapshot(
        hotspots=[{"path": "src/billing/pay.py", "summary": "complex"}]
    )
    const = _constitution(
        never_touch=[{"path": "src/billing/**", "reason": "human review"}]
    )
    opp = _only(_generate(snap, const), "complexity_reduction")

    assert opp["risk_tier"] == "tier_3_advisory"
    assert any(b.startswith("never_touch:") for b in opp["blocked_by"])


def test_ignored_paths_are_excluded():
    snap = _snapshot(
        hotspots=[
            {"path": "node_modules/x/index.js", "summary": "vendored"},
            {"path": "core/real.py", "summary": "real"},
        ]
    )
    const = _constitution(ignored_paths=["node_modules/**"])
    opportunities = _generate(snap, const)

    paths = {p for o in opportunities for p in o["affected_paths"]}
    assert "core/real.py" in paths
    assert all("node_modules" not in p for p in paths)


def test_aggregates_by_category_and_module():
    snap = _snapshot(
        hotspots=[
            {"path": "core/services/a.py", "summary": "x"},
            {"path": "core/services/b.py", "summary": "y"},
        ]
    )
    opportunities = [o for o in _generate(snap) if o["category"] == "complexity_reduction"]

    # Two files, same (category, module=core/services) -> one opportunity.
    assert len(opportunities) == 1
    assert set(opportunities[0]["affected_paths"]) == {
        "core/services/a.py",
        "core/services/b.py",
    }


def test_bounded_by_top_n_and_deterministic():
    snap = _snapshot(
        hotspots=[{"path": f"pkg{i}/file.py", "summary": "x", "score": i} for i in range(10)]
    )
    first = _generate(snap, top_n=3)
    second = _generate(snap, top_n=3)

    assert len(first) == 3
    assert first == second


def test_evidence_shape():
    snap = _snapshot(test_gaps=[{"path": "core/models.py", "summary": "no test"}])
    opp = _only(_generate(snap), "tests")

    ev = opp["evidence"][0]
    assert ev["source_type"] == "file"
    assert ev["path"] == "core/models.py"
    assert ev["summary"]
