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
            "dependency_cycles": _dependency_cycles(
                index_result.health,
                index_result.knowledge_graph,
            ),
            "hotspots": _health_hotspots(index_result.health),
            "dead_code_candidates": _dead_code_candidates(index_result.dead_code),
            "ownership_risks": _ownership_risks(index_result.repo_path),
            "test_gaps": _test_gaps(index_result.health),
            "dependency_risks": _dependency_risks(index_result.repo_path, index_result.health),
            "ci_failures": _ci_failures(index_result.repo_path, index_result.health),
        },
        "constitution_id": constitution_id,
    }


_DEFAULT_TIMEOUT_SECONDS = 600


def _run(
    command: list[str], timeout: float | None = _DEFAULT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            # Isolate stdin so Repowise never blocks on an interactive TTY prompt
            # (its init checks sys.stdin.isatty()); driven programmatically it must
            # run non-interactively instead of hanging at 0% CPU.
            stdin=subprocess.DEVNULL,
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


_SOURCE_EXTENSIONS = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
        ".rb", ".php", ".cs", ".kt", ".swift", ".scala", ".c", ".cc",
        ".cpp", ".h", ".hpp", ".vue", ".svelte",
    }
)

# Containers whose immediate children are the real logical systems (monorepo).
_MONOREPO_PARENTS = frozenset({"apps", "packages", "services", "libs"})

_ACRONYMS = frozenset({"api", "ui", "db", "cli", "sdk", "http", "ml", "ai", "css"})


def _system_name(name: str) -> str:
    if name.lower() in _ACRONYMS:
        return name.upper()
    return _display_name(name)


def _infer_logical_systems(repo_path: Path) -> list[JsonObject]:
    source_paths = [
        path
        for path in _tracked_source_paths(repo_path)
        if Path(path).suffix in _SOURCE_EXTENSIONS
    ]

    # Group source files into logical systems by their top-level directory,
    # expanding monorepo containers (apps/, packages/, ...) one level deeper.
    groups: dict[tuple[str, str], None] = {}
    for path in source_paths:
        parts = path.split("/")
        if len(parts) == 1:
            key = ("root", "root")
        elif parts[0] in _MONOREPO_PARENTS and len(parts) >= 3:
            prefix = f"{parts[0]}/{parts[1]}"
            key = (prefix, parts[1])
        else:
            key = (parts[0], parts[0])
        groups[key] = None

    systems: list[JsonObject] = []
    for prefix, name in sorted(groups):
        glob = "**" if prefix == "root" else f"{prefix}/**"
        systems.append(
            {
                "logical_system_id": f"sys_{_slug(name)}",
                "name": _system_name(name),
                "paths": [glob],
            }
        )

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
            summary = f"Repowise health score {score}."
            hotspots.append(
                {
                    "kind": "low_health_score",
                    "path": metric.get("file_path"),
                    "score": score,
                    "summary": summary,
                    "evidence": _evidence(metric.get("file_path"), summary),
                }
            )

    for finding in health.get("findings", []):
        if not isinstance(finding, dict):
            continue
        if _is_architectural(finding):
            continue  # routed to dependency_cycles instead
        summary = finding.get("reason") or "Repowise health finding."
        hotspots.append(
            {
                "kind": finding.get("biomarker_type", "health_finding"),
                "path": finding.get("file_path"),
                "score": finding.get("health_impact"),
                "severity": finding.get("severity"),
                "summary": summary,
                "evidence": _evidence(finding.get("file_path"), summary),
            }
        )
    return hotspots


def _evidence(path: Any, summary: str) -> list[JsonObject]:
    if not isinstance(path, str) or not path:
        return []
    return [{"source_type": "file", "path": path, "summary": summary}]


_ARCH_KEYWORDS = ("cycle", "coupling", "layer", "boundary")
_DEPENDENCY_KEYWORDS = (
    "dependency",
    "package",
    "lockfile",
    "outdated",
    "advisory",
    "vulnerability",
    "license",
)
_CI_KEYWORDS = ("ci", "workflow", "check", "pipeline", "build failed", "test failed")
_CI_TEST_COMMANDS = (
    "pytest",
    "python -m pytest",
    "npm test",
    "pnpm test",
    "yarn test",
    "vitest",
    "playwright",
    "ruff",
)


def _is_architectural(finding: JsonObject) -> bool:
    haystack = " ".join(
        str(finding.get(key, ""))
        for key in ("biomarker_type", "reason", "details")
    ).lower()
    return any(keyword in haystack for keyword in _ARCH_KEYWORDS)


def _dependency_cycles(
    health: JsonObject,
    knowledge_graph: JsonObject | None = None,
) -> list[JsonObject]:
    """Architecture signals (cycles, coupling, layer/boundary violations) lifted
    from Repowise health findings into the architecture entropy bucket."""
    cycles: list[JsonObject] = []
    for finding in health.get("findings", []):
        if not isinstance(finding, dict) or not _is_architectural(finding):
            continue
        summary = finding.get("reason") or "Repowise architecture finding."
        cycles.append(
            {
                "kind": finding.get("biomarker_type", "architecture_finding"),
                "path": finding.get("file_path"),
                "score": finding.get("health_impact"),
                "severity": finding.get("severity"),
                "summary": summary,
                "evidence": _evidence(finding.get("file_path"), summary),
            }
        )
    cycles.extend(_knowledge_graph_cycles(knowledge_graph or {}))
    return cycles


def _knowledge_graph_cycles(knowledge_graph: JsonObject) -> list[JsonObject]:
    edges = knowledge_graph.get("edges", [])
    if not isinstance(edges, list):
        return []

    graph: dict[str, set[str]] = {}
    node_paths = _knowledge_graph_file_paths(knowledge_graph)
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("type") != "imports":
            continue
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if not source.startswith("file:") or not target.startswith("file:"):
            continue
        graph.setdefault(source, set()).add(target)

    cycles: list[JsonObject] = []
    for component in _strongly_connected_components(graph):
        if len(component) < 2:
            continue
        paths = sorted(node_paths.get(node, node.removeprefix("file:")) for node in component)
        summary = f"Import cycle across {len(paths)} files."
        cycles.append(
            {
                "kind": "import_cycle",
                "path": paths[0],
                "severity": "high",
                "summary": summary,
                "cycle_paths": paths,
                "evidence": [_evidence(paths[0], summary)[0]],
            }
        )
        if len(cycles) >= 50:
            break
    return cycles


def _knowledge_graph_file_paths(knowledge_graph: JsonObject) -> dict[str, str]:
    paths: dict[str, str] = {}
    nodes = knowledge_graph.get("nodes", [])
    if not isinstance(nodes, list):
        return paths
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        file_path = node.get("filePath")
        if isinstance(node_id, str) and isinstance(file_path, str):
            paths[node_id] = file_path
    return paths


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                current = stack.pop()
                on_stack.remove(current)
                component.append(current)
                if current == node:
                    break
            components.append(component)

    for node in sorted(set(graph) | {n for neighbors in graph.values() for n in neighbors}):
        if node not in indices:
            visit(node)
    return components


def _dead_code_candidates(dead_code: list[JsonObject] | JsonObject) -> list[JsonObject]:
    findings = dead_code if isinstance(dead_code, list) else dead_code.get("findings", [])
    if not isinstance(findings, list):
        return []

    candidates: list[JsonObject] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        summary = finding.get("reason") or "Repowise dead-code finding."
        candidates.append(
            {
                "kind": finding.get("kind", "dead_code"),
                "path": finding.get("file_path"),
                "symbol": finding.get("symbol_name"),
                "confidence": finding.get("confidence"),
                "safe_to_delete": finding.get("safe_to_delete"),
                "summary": summary,
                "evidence": _evidence(finding.get("file_path"), summary),
            }
        )
    return candidates


def _test_gaps(health: JsonObject) -> list[JsonObject]:
    gaps: list[JsonObject] = []
    for metric in health.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        path = metric.get("file_path")
        if (
            metric.get("has_test_file") is False
            and isinstance(path, str)
            and _is_test_gap_target(path)
        ):
            summary = "Repowise did not find a paired test file."
            gaps.append(
                {
                    "kind": "missing_test_file",
                    "path": path,
                    "summary": summary,
                    "evidence": _evidence(path, summary),
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
        path = finding.get("file_path")
        if isinstance(path, str) and path and not _is_test_gap_target(path):
            continue
        if any(keyword in haystack for keyword in keywords):
            summary = finding.get("reason") or "Repowise testing signal."
            gaps.append(
                {
                    "kind": finding.get("biomarker_type", "test_gap"),
                    "path": path,
                    "severity": finding.get("severity"),
                    "summary": summary,
                    "evidence": _evidence(path, summary),
                }
            )
    return gaps


def _is_test_gap_target(path: str) -> bool:
    relative = Path(path)
    if relative.suffix.lower() not in _SOURCE_EXTENSIONS:
        return False

    parts = {part.lower() for part in relative.parts}
    if parts & {"test", "tests", "__tests__", "spec", "specs"}:
        return False

    name = relative.name.lower()
    return not (
        name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
    )


_DEPENDENCY_MANIFESTS = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "poetry.lock",
        "Pipfile",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "Gemfile",
        "composer.json",
    }
)
_LOCKFILES = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "requirements.txt",
        "go.sum",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
    }
)


def _dependency_risks(repo_path: Path, health: JsonObject) -> list[JsonObject]:
    risks: list[JsonObject] = []
    files = _tracked_source_paths(repo_path)
    manifests = [
        path
        for path in files
        if Path(path).name in _DEPENDENCY_MANIFESTS or Path(path).name.endswith(".csproj")
    ]
    lockfiles = {path for path in files if Path(path).name in _LOCKFILES}

    for manifest in manifests:
        if _manifest_has_lockfile(manifest, lockfiles):
            continue
        summary = f"Dependency manifest {manifest} has no nearby lockfile."
        risks.append(
            {
                "kind": "dependency_manifest_without_lockfile",
                "path": manifest,
                "severity": "medium",
                "summary": summary,
                "evidence": _evidence(manifest, summary),
            }
        )

    for finding in _keyword_findings(health, _DEPENDENCY_KEYWORDS):
        summary = finding.get("reason") or "Repowise dependency signal."
        path = finding.get("file_path")
        risks.append(
            {
                "kind": finding.get("biomarker_type", "dependency_risk"),
                "path": path,
                "score": finding.get("health_impact"),
                "severity": finding.get("severity"),
                "summary": summary,
                "evidence": _evidence(path, summary),
            }
        )

    return _dedupe_signals(risks)


def _manifest_has_lockfile(manifest: str, lockfiles: set[str]) -> bool:
    manifest_path = Path(manifest)
    parent = "" if str(manifest_path.parent) == "." else manifest_path.parent.as_posix()
    for lockfile in lockfiles:
        lock_path = Path(lockfile)
        lock_parent = "" if str(lock_path.parent) == "." else lock_path.parent.as_posix()
        if lock_parent == parent:
            return True
    return False


def _ci_failures(repo_path: Path, health: JsonObject) -> list[JsonObject]:
    failures: list[JsonObject] = []
    ci_files = _ci_config_files(repo_path)
    if not ci_files:
        summary = "No CI workflow configuration was detected."
        failures.append(
            {
                "kind": "missing_ci_config",
                "path": "",
                "severity": "medium",
                "summary": summary,
                "evidence": [],
            }
        )
    else:
        for path in ci_files:
            text = (repo_path / path).read_text(encoding="utf-8", errors="ignore").lower()
            if any(command in text for command in _CI_TEST_COMMANDS):
                continue
            summary = f"CI configuration {path} does not appear to run tests."
            failures.append(
                {
                    "kind": "ci_without_tests",
                    "path": path,
                    "severity": "medium",
                    "summary": summary,
                    "evidence": _evidence(path, summary),
                }
            )

    for finding in _keyword_findings(health, _CI_KEYWORDS):
        summary = finding.get("reason") or "Repowise CI signal."
        path = finding.get("file_path")
        failures.append(
            {
                "kind": finding.get("biomarker_type", "ci_signal"),
                "path": path,
                "score": finding.get("health_impact"),
                "severity": finding.get("severity"),
                "summary": summary,
                "evidence": _evidence(path, summary),
            }
        )
    return _dedupe_signals(failures)


def _ci_config_files(repo_path: Path) -> list[str]:
    candidates: list[str] = []
    workflow_dir = repo_path / ".github" / "workflows"
    if workflow_dir.exists():
        for path in sorted(workflow_dir.glob("*")):
            if path.suffix.lower() in {".yml", ".yaml"} and path.is_file():
                candidates.append(path.relative_to(repo_path).as_posix())
    for name in (".gitlab-ci.yml", "bitbucket-pipelines.yml", "Jenkinsfile"):
        if (repo_path / name).is_file():
            candidates.append(name)
    return candidates


def _ownership_risks(repo_path: Path) -> list[JsonObject]:
    authors = _git_lines(repo_path, ["log", "--format=%ae", "--all", "-n", "500"])
    author_counts: dict[str, int] = {}
    for author in authors:
        if author:
            author_counts[author] = author_counts.get(author, 0) + 1

    risks: list[JsonObject] = []
    total_commits = sum(author_counts.values())
    if total_commits and len(author_counts) <= 1:
        summary = "Repository history shows only one recent committer."
        risks.append(
            {
                "kind": "low_bus_factor",
                "path": "",
                "severity": "high",
                "summary": summary,
                "commit_count": total_commits,
                "author_count": len(author_counts),
                "evidence": [],
            }
        )

    file_authors = _file_author_counts(repo_path)
    for path, counts in sorted(file_authors.items()):
        total = sum(counts.values())
        if total < 3:
            continue
        lead_author, lead_count = max(counts.items(), key=lambda item: item[1])
        concentration = lead_count / total
        if concentration < 0.85:
            continue
        summary = f"{round(concentration * 100)}% of recent edits are by one author."
        risks.append(
            {
                "kind": "ownership_concentration",
                "path": path,
                "severity": "medium",
                "summary": summary,
                "lead_author": lead_author,
                "touch_count": total,
                "evidence": _evidence(path, summary),
            }
        )
        if len(risks) >= 50:
            break
    return risks


def _file_author_counts(repo_path: Path) -> dict[str, dict[str, int]]:
    lines = _git_lines(
        repo_path,
        ["log", "--name-only", "--format=author:%ae", "--all", "-n", "500"],
    )
    current_author = ""
    counts: dict[str, dict[str, int]] = {}
    for line in lines:
        if line.startswith("author:"):
            current_author = line.removeprefix("author:")
            continue
        if not line or not current_author:
            continue
        path = line.strip()
        if Path(path).suffix not in _SOURCE_EXTENSIONS:
            continue
        counts.setdefault(path, {})
        counts[path][current_author] = counts[path].get(current_author, 0) + 1
    return counts


def _git_lines(repo_path: Path, args: list[str]) -> list[str]:
    try:
        result = _run(["git", "-C", str(repo_path), *args], timeout=60)
    except RepowiseCommandError:
        return []
    return result.stdout.splitlines()


def _keyword_findings(health: JsonObject, keywords: tuple[str, ...]) -> list[JsonObject]:
    findings: list[JsonObject] = []
    for finding in health.get("findings", []):
        if not isinstance(finding, dict):
            continue
        haystack = " ".join(
            str(finding.get(key, ""))
            for key in ("biomarker_type", "reason", "details")
        ).lower()
        if any(keyword in haystack for keyword in keywords):
            findings.append(finding)
    return findings


def _dedupe_signals(signals: list[JsonObject]) -> list[JsonObject]:
    deduped: list[JsonObject] = []
    seen: set[tuple[str, str, str]] = set()
    for signal in signals:
        key = (
            str(signal.get("kind", "")),
            str(signal.get("path", "")),
            str(signal.get("summary", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)
    return deduped


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
