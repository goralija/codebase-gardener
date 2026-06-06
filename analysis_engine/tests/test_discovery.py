from __future__ import annotations

from pathlib import Path

from gardener_analysis import (
    SourceTruthDiscovery,
    SourceTruthFile,
    discover_source_truth,
    load_fixture_repository,
)


def _discover_fixture(name: str) -> SourceTruthDiscovery:
    return discover_source_truth(load_fixture_repository(name).path)


def _categories(discovery: SourceTruthDiscovery) -> set[str]:
    return {file.category for file in discovery.files}


def test_complete_normal_repo_finds_constitution_readme_and_manifest():
    discovery = _discover_fixture("normal_repo")

    found = _categories(discovery)
    assert {"constitution", "readme", "package_manifest"} <= found
    assert "constitution" not in discovery.categories_missing
    assert "readme" not in discovery.categories_missing


def test_complete_monorepo_also_finds_architecture():
    discovery = _discover_fixture("monorepo_repo")

    found = _categories(discovery)
    assert {"constitution", "readme", "architecture", "package_manifest"} <= found
    assert "architecture" in discovery.categories_found


def test_partial_protected_modules_repo_misses_architecture():
    discovery = _discover_fixture("protected_modules_repo")

    found = _categories(discovery)
    assert {"constitution", "readme"} <= found
    assert "architecture" not in found
    assert "architecture" in discovery.categories_missing


def test_missing_docs_repo_reports_missing_doc_categories():
    discovery = _discover_fixture("missing_docs_repo")

    found = _categories(discovery)
    assert "constitution" not in found
    assert "readme" not in found
    assert "architecture" not in found
    assert {"constitution", "readme", "architecture"} <= set(discovery.categories_missing)


def test_conflicting_docs_repo_flags_multiple_architecture_sources():
    discovery = _discover_fixture("conflicting_docs_repo")

    found = _categories(discovery)
    assert {"constitution", "architecture"} <= found
    assert "multiple_architecture_sources" in discovery.conflict_hints


def _make_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def test_synthetic_repo_classifies_exotic_categories(tmp_path: Path):
    repo = _make_repo(
        tmp_path / "repo",
        {
            "docs/adr/0001-choose-db.md": "# ADR",
            ".claude/rules.md": "rules",
            ".github/CODEOWNERS": "* @team",
            ".github/workflows/ci.yml": "name: ci",
            "AGENTS.md": "agents",
            "CONTRIBUTING.md": "contrib",
            "src/app.py": "x = 1",
        },
    )

    discovery = discover_source_truth(repo)
    by_path = {file.path: file.category for file in discovery.files}

    assert by_path["docs/adr/0001-choose-db.md"] == "adr"
    assert by_path[".claude/rules.md"] == "agents_dir"
    assert by_path[".github/CODEOWNERS"] == "code_owners"
    assert by_path[".github/workflows/ci.yml"] == "ci_config"
    assert by_path["AGENTS.md"] == "agents_doc"
    assert by_path["CONTRIBUTING.md"] == "contributing"
    assert "src/app.py" not in by_path


def test_ignored_directories_are_skipped(tmp_path: Path):
    repo = _make_repo(
        tmp_path / "repo",
        {
            "README.md": "real",
            "node_modules/pkg/README.md": "vendored",
            ".venv/lib/ARCHITECTURE.md": "venv",
        },
    )

    discovery = discover_source_truth(repo)
    paths = {file.path for file in discovery.files}

    assert paths == {"README.md"}


def test_discovery_is_sorted_and_deterministic(tmp_path: Path):
    repo = _make_repo(
        tmp_path / "repo",
        {
            "README.md": "r",
            "ARCHITECTURE.md": "a",
            "GARDENER.md": "g",
        },
    )

    first = discover_source_truth(repo)
    second = discover_source_truth(repo)

    assert first == second
    assert [file.path for file in first.files] == sorted(
        file.path for file in first.files
    )


def test_source_truth_file_to_evidence_shape():
    evidence = SourceTruthFile(
        category="architecture",
        path="ARCHITECTURE.md",
        summary="Source-truth architecture file at ARCHITECTURE.md.",
    ).to_evidence()

    assert evidence["source_type"] == "file"
    assert evidence["path"] == "ARCHITECTURE.md"
    assert "summary" in evidence
