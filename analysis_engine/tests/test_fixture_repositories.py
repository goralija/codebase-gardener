from pathlib import Path

import pytest

from gardener_analysis import load_fixture_repository
from gardener_analysis.fixtures import list_fixture_repositories


EXPECTED_FIXTURES = {
    "normal_repo",
    "monorepo_repo",
    "missing_docs_repo",
    "conflicting_docs_repo",
    "protected_modules_repo",
}


SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js"}


def parseable_source_files(path: Path) -> list[Path]:
    return [
        source_path
        for source_path in path.rglob("*")
        if source_path.is_file() and source_path.suffix in SOURCE_EXTENSIONS
    ]


def test_all_expected_fixture_repositories_are_discoverable():
    fixtures = list_fixture_repositories()

    assert {fixture.name for fixture in fixtures} == EXPECTED_FIXTURES
    assert [fixture.name for fixture in fixtures] == sorted(EXPECTED_FIXTURES)


def test_fixture_repositories_exist_and_have_parseable_source():
    for fixture in list_fixture_repositories():
        assert fixture.path.exists(), fixture.name
        assert fixture.path.is_dir(), fixture.name
        assert parseable_source_files(fixture.path), fixture.name


def test_documented_fixture_repositories_include_gardener_constitution():
    for name in ("normal_repo", "monorepo_repo", "protected_modules_repo"):
        fixture = load_fixture_repository(name)
        assert (fixture.path / "GARDENER.md").is_file()


def test_missing_docs_fixture_intentionally_lacks_source_truth_docs():
    fixture = load_fixture_repository("missing_docs_repo")

    assert not (fixture.path / "README.md").exists()
    assert not (fixture.path / "GARDENER.md").exists()
    assert not (fixture.path / "ARCHITECTURE.md").exists()


def test_conflicting_docs_fixture_contains_conflicting_source_truth_files():
    fixture = load_fixture_repository("conflicting_docs_repo")

    gardener = (fixture.path / "GARDENER.md").read_text()
    architecture = (fixture.path / "ARCHITECTURE.md").read_text()

    assert "Frontend may import persistence models" in gardener
    assert "Frontend must not import persistence models" in architecture


def test_load_fixture_repository_returns_named_fixture():
    fixture = load_fixture_repository("normal_repo")

    assert fixture.name == "normal_repo"
    assert fixture.path.name == "normal_repo"
    assert "documented" in fixture.tags


def test_load_fixture_repository_rejects_unknown_fixture():
    with pytest.raises(ValueError, match="Unknown fixture repository 'unknown_repo'"):
        load_fixture_repository("unknown_repo")
