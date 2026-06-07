from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

import gardener_analysis.repowise as repowise
from gardener_analysis import (
    RepowiseCommandError,
    RepowiseIndexOptions,
    build_analysis_snapshot,
    index_repository,
    load_fixture_repository,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOWISE_PROJECT = PROJECT_ROOT / "RepoWise"


def test_normal_repo_indexes_and_builds_valid_analysis_snapshot(tmp_path: Path):
    repo_path = _copy_fixture_as_git_repo("normal_repo", tmp_path)

    result = index_repository(
        repo_path,
        RepowiseIndexOptions(repowise_project=REPOWISE_PROJECT),
    )
    snapshot = build_analysis_snapshot(
        result,
        repository_id="repo_normal",
        constitution_id="constitution_normal",
        created_at=datetime(2026, 6, 6, 12, 0, tzinfo=UTC),
    )

    assert (repo_path / ".repowise" / "state.json").exists()
    assert result.commit_sha
    _validate_analysis_snapshot(snapshot)
    assert snapshot["repository_id"] == "repo_normal"
    assert snapshot["constitution_id"] == "constitution_normal"


def test_monorepo_snapshot_infers_api_web_and_shared_systems(tmp_path: Path):
    repo_path = _copy_fixture_as_git_repo("monorepo_repo", tmp_path)

    result = index_repository(
        repo_path,
        RepowiseIndexOptions(repowise_project=REPOWISE_PROJECT),
    )
    snapshot = build_analysis_snapshot(
        result,
        repository_id="repo_monorepo",
        constitution_id="constitution_monorepo",
        created_at=datetime(2026, 6, 6, 12, 0, tzinfo=UTC),
    )

    systems = {system["name"]: system for system in snapshot["logical_systems"]}
    assert "API" in systems
    assert "Web" in systems
    assert "Shared" in systems
    assert systems["API"]["paths"] == ["apps/api/**"]
    assert systems["Web"]["paths"] == ["apps/web/**"]
    assert systems["Shared"]["paths"] == ["packages/shared/**"]


def test_missing_docs_repo_still_indexes_and_snapshots(tmp_path: Path):
    repo_path = _copy_fixture_as_git_repo("missing_docs_repo", tmp_path)

    result = index_repository(
        repo_path,
        RepowiseIndexOptions(repowise_project=REPOWISE_PROJECT),
    )
    snapshot = build_analysis_snapshot(
        result,
        repository_id="repo_missing_docs",
        constitution_id="constitution_missing_docs",
        created_at=datetime(2026, 6, 6, 12, 0, tzinfo=UTC),
    )

    _validate_analysis_snapshot(snapshot)
    assert snapshot["logical_systems"]


def test_failed_repowise_command_raises_clear_error(monkeypatch):
    def fake_run(command, capture_output, text, check, timeout=None, **kwargs):
        return subprocess.CompletedProcess(
            args=command,
            returncode=42,
            stdout="stdout details",
            stderr="stderr details",
        )

    monkeypatch.setattr(repowise.subprocess, "run", fake_run)

    try:
        repowise._run(["uv", "--project", "RepoWise", "run", "repowise", "health"])
    except RepowiseCommandError as error:
        assert error.command == ["uv", "--project", "RepoWise", "run", "repowise", "health"]
        assert error.exit_code == 42
        assert error.stdout_excerpt == "stdout details"
        assert error.stderr_excerpt == "stderr details"
        assert "exit_code=42" in str(error)
    else:
        raise AssertionError("Expected RepowiseCommandError.")


def test_dead_code_parser_extracts_final_json_payload_from_noisy_stdout():
    stdout = "repowise dead-code - /tmp/repo\nTip text\n[\n  {\"kind\": \"unused_export\", \"file_path\": \"src/a.py\"}\n]\n"

    parsed = repowise._parse_final_json_stdout(stdout)

    assert parsed == [{"kind": "unused_export", "file_path": "src/a.py"}]


def test_test_gap_parser_ignores_source_truth_docs_and_existing_tests():
    health = {
        "metrics": [
            {"file_path": "GARDENER.md", "has_test_file": False},
            {"file_path": "docs/guide.md", "has_test_file": False},
            {"file_path": "tests/test_service.py", "has_test_file": False},
            {"file_path": "src/service.py", "has_test_file": False},
        ],
        "findings": [
            {
                "biomarker_type": "untested_hotspot",
                "file_path": "GARDENER.md",
                "reason": "No paired test.",
            },
            {
                "biomarker_type": "untested_hotspot",
                "file_path": "frontend/src/use-report.ts",
                "reason": "No paired test.",
            },
        ],
    }

    gaps = repowise._test_gaps(health)

    assert [gap["path"] for gap in gaps] == [
        "src/service.py",
        "frontend/src/use-report.ts",
    ]


def test_snapshot_extracts_dependency_ci_ownership_and_graph_cycle_signals(tmp_path: Path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "package.json").write_text('{"dependencies":{"left-pad":"1.0.0"}}\n')
    (repo_path / ".github" / "workflows").mkdir(parents=True)
    (repo_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\non: [push]\njobs:\n  build:\n    steps:\n      - run: echo build\n",
        encoding="utf-8",
    )
    (repo_path / "src").mkdir()
    (repo_path / "src" / "a.py").write_text("import src.b\n", encoding="utf-8")
    (repo_path / "src" / "b.py").write_text("import src.a\n", encoding="utf-8")
    _git(repo_path, "init")
    _git(repo_path, "add", ".")
    for index in range(3):
        (repo_path / "src" / "a.py").write_text(f"import src.b\n# {index}\n")
        _git(repo_path, "add", ".")
        _git(
            repo_path,
            "-c",
            "user.name=Solo",
            "-c",
            "user.email=solo@example.com",
            "commit",
            "-m",
            f"Commit {index}",
        )

    index_result = repowise.RepowiseIndexResult(
        repo_path=repo_path,
        commit_sha=_git_stdout(repo_path, "rev-parse", "HEAD"),
        state={},
        knowledge_graph={
            "nodes": [
                {"id": "file:src/a.py", "filePath": "src/a.py"},
                {"id": "file:src/b.py", "filePath": "src/b.py"},
            ],
            "edges": [
                {"source": "file:src/a.py", "target": "file:src/b.py", "type": "imports"},
                {"source": "file:src/b.py", "target": "file:src/a.py", "type": "imports"},
            ],
        },
        health={
            "metrics": [],
            "findings": [
                {
                    "biomarker_type": "dependency_signal",
                    "file_path": "package.json",
                    "reason": "Dependency package drift detected.",
                    "severity": "medium",
                }
            ],
        },
        dead_code=[],
    )

    snapshot = build_analysis_snapshot(
        index_result,
        repository_id="repo_full",
        constitution_id="constitution_full",
        created_at=datetime(2026, 6, 6, 12, 0, tzinfo=UTC),
    )
    signals = snapshot["signals"]

    assert any(s["kind"] == "import_cycle" for s in signals["dependency_cycles"])
    assert any(
        s["kind"] == "dependency_manifest_without_lockfile"
        for s in signals["dependency_risks"]
    )
    assert any(s["kind"] == "ci_without_tests" for s in signals["ci_failures"])
    assert any(s["kind"] == "low_bus_factor" for s in signals["ownership_risks"])
    assert any(
        s["kind"] == "ownership_concentration"
        for s in signals["ownership_risks"]
    )
    _validate_analysis_snapshot(snapshot)


def _copy_fixture_as_git_repo(name: str, tmp_path: Path) -> Path:
    fixture = load_fixture_repository(name)
    repo_path = tmp_path / name
    shutil.copytree(fixture.path, repo_path)
    _git(repo_path, "init")
    _git(repo_path, "add", ".")
    _git(
        repo_path,
        "-c",
        "user.name=Fixture Test",
        "-c",
        "user.email=fixture@example.com",
        "commit",
        "-m",
        "Initial fixture repo",
    )
    return repo_path


def _git(repo_path: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _git_stdout(repo_path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _validate_analysis_snapshot(snapshot: dict) -> None:
    schema_path = PROJECT_ROOT / "fixtures" / "schemas" / "analysis_snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(snapshot)
