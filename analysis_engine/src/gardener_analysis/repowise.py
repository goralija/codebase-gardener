from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class RepowiseIndexOptions:
    repowise_project: Path
    mode: Literal["fast", "standard"] = "fast"


@dataclass(frozen=True)
class RepowiseIndexResult:
    repo_path: Path
    commit_sha: str
    state: JsonObject
    knowledge_graph: JsonObject | None
    health: JsonObject
    dead_code: list[JsonObject] | JsonObject


class RepowiseCommandError(RuntimeError):
    def __init__(
        self,
        command: list[str],
        exit_code: int,
        stdout_excerpt: str,
        stderr_excerpt: str,
    ) -> None:
        self.command = command
        self.exit_code = exit_code
        self.stdout_excerpt = stdout_excerpt
        self.stderr_excerpt = stderr_excerpt
        super().__init__(
            "Repowise command failed: "
            f"command={_format_command(command)!r}, "
            f"exit_code={exit_code}, "
            f"stdout={stdout_excerpt!r}, "
            f"stderr={stderr_excerpt!r}"
        )


def index_repository(repo_path: Path, options: RepowiseIndexOptions) -> RepowiseIndexResult:
    repo_path = repo_path.resolve()
    repowise_project = options.repowise_project.resolve()

    _run(
        [
            "uv",
            "--project",
            str(repowise_project),
            "run",
            "repowise",
            "init",
            str(repo_path),
            "--index-only",
            "--mode",
            options.mode,
            "--yes",
            "--no-agents",
            "--no-codex",
            "--no-claude-md",
            "--no-distill-hook",
        ]
    )
    health = _parse_json_stdout(
        _run(
            [
                "uv",
                "--project",
                str(repowise_project),
                "run",
                "repowise",
                "health",
                str(repo_path),
                "--format",
                "json",
                "--no-workspace",
            ]
        ).stdout
    )
    dead_code = _parse_final_json_stdout(
        _run(
            [
                "uv",
                "--project",
                str(repowise_project),
                "run",
                "repowise",
                "dead-code",
                str(repo_path),
                "--format",
                "json",
                "--no-workspace",
            ]
        ).stdout
    )

    state_path = repo_path / ".repowise" / "state.json"
    if not state_path.exists():
        raise RepowiseCommandError(
            command=["repowise", "init", str(repo_path)],
            exit_code=0,
            stdout_excerpt="",
            stderr_excerpt=f"Expected Repowise state file at {state_path}, none found.",
        )
    state = _read_json_object(state_path)
    knowledge_graph_path = repo_path / ".repowise" / "knowledge-graph.json"
    knowledge_graph = (
        _read_json_object(knowledge_graph_path) if knowledge_graph_path.exists() else None
    )

    return RepowiseIndexResult(
        repo_path=repo_path,
        commit_sha=_git_head(repo_path),
        state=state,
        knowledge_graph=knowledge_graph,
        health=health,
        dead_code=dead_code,
    )


def build_analysis_snapshot(
    index_result: RepowiseIndexResult,
    repository_id: str,
    constitution_id: str,
    created_at: datetime | None = None,
) -> JsonObject:
    created_at = created_at or datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    return {
        "schema_version": "1.0",
        "analysis_snapshot_id": f"snap_{index_result.commit_sha[:12]}",
        "repository_id": repository_id,
        "commit_sha": index_result.commit_sha,
        "created_at": _format_datetime(created_at),
        "logical_systems": _infer_logical_systems(index_result.repo_path),
        "signals": {
            "dependency_cycles": [],
            "hotspots": _health_hotspots(index_result.health),
            "dead_code_candidates": _dead_code_candidates(index_result.dead_code),
            "ownership_risks": [],
            "test_gaps": _test_gaps(index_result.health),
            "dependency_risks": [],
            "ci_failures": [],
        },
        "constitution_id": constitution_id,
    }


_DEFAULT_TIMEOUT_SECONDS = 600


def _run(
    command: list[str], timeout: float | None = _DEFAULT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise RepowiseCommandError(
            command=command,
            exit_code=-1,
            stdout_excerpt=_excerpt(exc.stdout or "" if isinstance(exc.stdout, str) else ""),
            stderr_excerpt=_excerpt(
                f"Timed out after {timeout}s. "
                + (exc.stderr if isinstance(exc.stderr, str) else "")
            ),
        ) from exc
    if result.returncode != 0:
        raise RepowiseCommandError(
            command=command,
            exit_code=result.returncode,
            stdout_excerpt=_excerpt(result.stdout),
            stderr_excerpt=_excerpt(result.stderr),
        )
    return result


def _git_head(repo_path: Path) -> str:
    return _run(["git", "-C", str(repo_path), "rev-parse", "HEAD"]).stdout.strip()


def _read_json_object(path: Path) -> JsonObject:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object at {path}.")
    return value


def _parse_json_stdout(stdout: str) -> JsonObject:
    value = json.loads(stdout)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object from Repowise command.")
    return value


def _parse_final_json_stdout(stdout: str) -> list[JsonObject] | JsonObject:
    trimmed = stdout.rstrip()
    if not trimmed or trimmed[-1] not in "]}":
        raise ValueError("Could not find final JSON payload in Repowise stdout.")

    decoder = json.JSONDecoder()
    opener = "[" if trimmed[-1] == "]" else "{"
    search_end = len(trimmed)
    value: Any = None
    while True:
        index = trimmed.rfind(opener, 0, search_end)
        if index == -1:
            raise ValueError("Could not find final JSON payload in Repowise stdout.")
        try:
            decoded, end = decoder.raw_decode(trimmed[index:])
        except json.JSONDecodeError:
            search_end = index
            continue
        if index + end != len(trimmed):
            search_end = index
            continue
        value = decoded
        break

    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return value
    raise ValueError("Expected final JSON array or object from Repowise command.")


def _infer_logical_systems(repo_path: Path) -> list[JsonObject]:
    paths = _tracked_source_paths(repo_path)
    systems: list[JsonObject] = []

    def add(system_id: str, name: str, glob: str, predicate: str) -> None:
        if any(path == predicate or path.startswith(f"{predicate}/") for path in paths):
            systems.append(
                {
                    "logical_system_id": system_id,
                    "name": name,
                    "paths": [glob],
                }
            )

    add("sys_api", "API", "apps/api/**", "apps/api")
    add("sys_web", "Web", "apps/web/**", "apps/web")

    package_names = sorted(
        {
            parts[1]
            for path in paths
            if (parts := path.split("/"))
            and len(parts) >= 3
            and parts[0] == "packages"
        }
    )
    for package in package_names:
        systems.append(
            {
                "logical_system_id": f"sys_{_slug(package)}",
                "name": _display_name(package),
                "paths": [f"packages/{package}/**"],
            }
        )

    add("sys_src", "Source", "src/**", "src")
    add("sys_tests", "Tests", "tests/**", "tests")

    if systems:
        return systems
    return [
        {
            "logical_system_id": "sys_repository",
            "name": "Repository",
            "paths": ["**"],
        }
    ]


_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".repowise",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        ".cache",
    }
)


def _tracked_source_paths(repo_path: Path) -> list[str]:
    paths: list[str] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_path)
        if any(part in _IGNORED_DIRS for part in relative.parts):
            continue
        paths.append(relative.as_posix())
    return sorted(paths)


def _health_hotspots(health: JsonObject) -> list[JsonObject]:
    hotspots: list[JsonObject] = []
    for metric in health.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        score = metric.get("score")
        if isinstance(score, int | float) and not isinstance(score, bool) and score < 7:
            hotspots.append(
                {
                    "kind": "low_health_score",
                    "path": metric.get("file_path"),
                    "score": score,
                    "summary": f"Repowise health score {score}.",
                }
            )

    for finding in health.get("findings", []):
        if not isinstance(finding, dict):
            continue
        hotspots.append(
            {
                "kind": finding.get("biomarker_type", "health_finding"),
                "path": finding.get("file_path"),
                "score": finding.get("health_impact"),
                "severity": finding.get("severity"),
                "summary": finding.get("reason") or "Repowise health finding.",
            }
        )
    return hotspots


def _dead_code_candidates(dead_code: list[JsonObject] | JsonObject) -> list[JsonObject]:
    findings = dead_code if isinstance(dead_code, list) else dead_code.get("findings", [])
    if not isinstance(findings, list):
        return []

    candidates: list[JsonObject] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        candidates.append(
            {
                "kind": finding.get("kind", "dead_code"),
                "path": finding.get("file_path"),
                "symbol": finding.get("symbol_name"),
                "confidence": finding.get("confidence"),
                "safe_to_delete": finding.get("safe_to_delete"),
                "summary": finding.get("reason") or "Repowise dead-code finding.",
            }
        )
    return candidates


def _test_gaps(health: JsonObject) -> list[JsonObject]:
    gaps: list[JsonObject] = []
    for metric in health.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        path = metric.get("file_path")
        if metric.get("has_test_file") is False and isinstance(path, str):
            gaps.append(
                {
                    "kind": "missing_test_file",
                    "path": path,
                    "summary": "Repowise did not find a paired test file.",
                }
            )

    keywords = ("test", "coverage", "untested")
    for finding in health.get("findings", []):
        if not isinstance(finding, dict):
            continue
        haystack = " ".join(
            str(finding.get(key, ""))
            for key in ("biomarker_type", "reason", "details")
        ).lower()
        if any(keyword in haystack for keyword in keywords):
            gaps.append(
                {
                    "kind": finding.get("biomarker_type", "test_gap"),
                    "path": finding.get("file_path"),
                    "severity": finding.get("severity"),
                    "summary": finding.get("reason") or "Repowise testing signal.",
                }
            )
    return gaps


def _format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


def _display_name(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def _excerpt(value: str, limit: int = 4000) -> str:
    collapsed = value.strip()
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[:limit]}..."


def _format_command(command: list[str]) -> str:
    return shlex.join(command)
