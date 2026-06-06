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


def _validate_analysis_snapshot(snapshot: dict) -> None:
    schema_path = PROJECT_ROOT / "fixtures" / "schemas" / "analysis_snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(snapshot)
