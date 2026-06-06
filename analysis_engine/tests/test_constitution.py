from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from gardener_analysis import (
    build_repository_constitution,
    load_fixture_repository,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    PROJECT_ROOT / "fixtures" / "schemas" / "repository_constitution.schema.json"
)


def _build(name: str) -> dict:
    return build_repository_constitution(
        load_fixture_repository(name).path,
        repository_id=f"repo_{name}",
        commit_sha="abc123",
    )


def _validate(constitution: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(constitution)


DOCUMENTED = ("normal_repo", "monorepo_repo", "protected_modules_repo")
ALL_FIXTURES = (*DOCUMENTED, "conflicting_docs_repo", "missing_docs_repo")


def test_all_fixtures_produce_schema_valid_constitutions():
    for name in ALL_FIXTURES:
        constitution = _build(name)
        _validate(constitution)
        assert constitution["schema_version"] == "1.0"
        assert constitution["repository_id"] == f"repo_{name}"
        assert constitution["commit_sha"] == "abc123"


def test_protected_modules_repo_parses_protected_and_never_touch():
    c = _build("protected_modules_repo")

    names = {module["name"].lower() for module in c["protected_modules"]}
    assert any("auth" in name for name in names)
    assert any("billing" in name for name in names)
    for module in c["protected_modules"]:
        assert module["paths"]

    never_paths = {entry["path"] for entry in c["never_touch"]}
    assert any("payment_engine.py" in path for path in never_paths)
    assert all(entry["reason"] for entry in c["never_touch"])

    assert "auth" in c["allowed_fixes"]["advisory"]
    assert "payments" in c["allowed_fixes"]["advisory"]


def test_monorepo_parses_boundaries_and_ignored_paths():
    c = _build("monorepo_repo")

    assert len(c["architecture_boundaries"]) >= 1
    assert "node_modules/**" in c["ignored_paths"]


def test_normal_repo_parses_allowed_autonomous_fixes():
    c = _build("normal_repo")

    autonomous = c["allowed_fixes"]["autonomous"]
    assert "docs" in autonomous
    assert "lint_format" in autonomous


def test_dead_code_removal_phrase_maps_to_dead_code_category(tmp_path):
    (tmp_path / "GARDENER.md").write_text(
        "\n".join(
            [
                "# GARDENER.md",
                "",
                "## Autonomous Fixes Allowed",
                "",
                "- dead code removal",
            ]
        ),
        encoding="utf-8",
    )

    c = build_repository_constitution(
        tmp_path,
        repository_id="repo_dead_code",
        commit_sha="abc123",
    )

    assert c["allowed_fixes"]["autonomous"] == ["dead_code"]


def test_boundary_rule_carries_file_evidence_with_section():
    c = _build("monorepo_repo")

    rule = c["architecture_boundaries"][0]
    evidence = rule["evidence"][0]
    assert evidence["source_type"] == "file"
    assert evidence["path"] == "GARDENER.md"
    assert evidence["section"] == "Architecture Boundaries"


def test_missing_docs_repo_is_empty_with_blocking_question():
    c = _build("missing_docs_repo")

    assert c["completeness_score"] == 0.0
    assert c["protected_modules"] == []
    assert c["architecture_boundaries"] == []
    blocking = [q for q in c["open_questions"] if q["severity"] == "blocking"]
    assert blocking
    assert any("constitution" in q["question"].lower() for q in blocking)


def test_conflicting_docs_repo_flags_conflict_without_silent_rule():
    c = _build("conflicting_docs_repo")

    blocking = [q for q in c["open_questions"] if q["severity"] == "blocking"]
    assert any("architecture" in q["question"].lower() for q in blocking)
    # Q2: disputed boundary must NOT be silently materialized.
    assert c["architecture_boundaries"] == []


def test_completeness_score_within_bounds_and_ordering():
    documented = _build("protected_modules_repo")["completeness_score"]
    missing = _build("missing_docs_repo")["completeness_score"]

    for score in (documented, missing):
        assert 0.0 <= score <= 1.0
    assert documented > missing


def test_build_is_deterministic():
    first = _build("monorepo_repo")
    second = _build("monorepo_repo")

    assert first == second
