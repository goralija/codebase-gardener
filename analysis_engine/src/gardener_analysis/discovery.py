from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class SourceTruthFile:
    category: str
    path: str
    summary: str

    def to_evidence(self) -> JsonObject:
        return {
            "source_type": "file",
            "path": self.path,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class SourceTruthDiscovery:
    repo_path: Path
    files: tuple[SourceTruthFile, ...]
    categories_found: tuple[str, ...]
    categories_missing: tuple[str, ...]
    conflict_hints: tuple[str, ...]


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

# Directories that are themselves source-truth and must NOT be skipped by the
# ignore walk even though they start with a dot.
_KEPT_DOT_DIRS = frozenset({".agents", ".claude", ".github"})

_ADR_DIRS = frozenset({"adr", "adrs", "decisions"})

# Ordered categories. The first one whose matcher returns True claims the file.
CATEGORIES: tuple[str, ...] = (
    "constitution",
    "readme",
    "architecture",
    "adr",
    "agents_doc",
    "agents_dir",
    "contributing",
    "code_owners",
    "package_manifest",
    "ci_config",
    "test_config",
)

# Document categories whose absence is meaningful for the constitution builder.
# (package/ci/test config presence varies too much to call "missing" useful.)
_REPORTED_MISSING: tuple[str, ...] = (
    "constitution",
    "readme",
    "architecture",
    "adr",
    "agents_doc",
    "agents_dir",
    "contributing",
    "code_owners",
)

_PACKAGE_MANIFESTS = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "pnpm-workspace.yaml",
        "cargo.toml",
        "go.mod",
    }
)

_TEST_CONFIGS = frozenset({"pytest.ini", "tox.ini"})
_TEST_CONFIG_PREFIXES = ("jest.config.", "vitest.config.")


def _parts_lower(relative: Path) -> tuple[str, ...]:
    return tuple(part.lower() for part in relative.parts)


def _classify(relative: Path) -> str | None:
    parts = _parts_lower(relative)
    name = parts[-1]
    dirs = parts[:-1]

    if name == "gardener.md":
        return "constitution"
    if name.startswith("readme"):
        return "readme"
    if name.startswith("architecture"):
        return "architecture"
    if any(part in _ADR_DIRS for part in dirs):
        return "adr"
    if name in ("agents.md", "claude.md"):
        return "agents_doc"
    if ".agents" in dirs or ".claude" in dirs:
        return "agents_dir"
    if name.startswith("contributing"):
        return "contributing"
    if name == "codeowners":
        return "code_owners"
    if name in _PACKAGE_MANIFESTS:
        return "package_manifest"
    if dirs[:2] == (".github", "workflows"):
        return "ci_config"
    if name == ".gitlab-ci.yml":
        return "ci_config"
    if name in _TEST_CONFIGS or name.startswith(_TEST_CONFIG_PREFIXES):
        return "test_config"
    return None


def _summary(category: str, path: str) -> str:
    return f"Source-truth {category} file at {path}."


def _walk(repo_path: Path) -> Iterable[Path]:
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_path)
        if any(
            part in _IGNORED_DIRS
            or (part.startswith(".") and part not in _KEPT_DOT_DIRS)
            for part in relative.parts[:-1]
        ):
            continue
        yield relative


def _conflict_hints(files: tuple[SourceTruthFile, ...]) -> tuple[str, ...]:
    hints: list[str] = []
    by_category: dict[str, list[str]] = {}
    for file in files:
        by_category.setdefault(file.category, []).append(file.path)

    if "architecture" in by_category and "constitution" in by_category:
        hints.append("multiple_architecture_sources")

    for category in CATEGORIES:
        if len(by_category.get(category, ())) > 1:
            hints.append(f"duplicate_{category}")

    return tuple(sorted(set(hints)))


def discover_source_truth(repo_path: Path) -> SourceTruthDiscovery:
    repo_path = repo_path.resolve()

    found: list[SourceTruthFile] = []
    for relative in _walk(repo_path):
        category = _classify(relative)
        if category is None:
            continue
        posix = relative.as_posix()
        found.append(
            SourceTruthFile(
                category=category,
                path=posix,
                summary=_summary(category, posix),
            )
        )

    files = tuple(sorted(found, key=lambda file: (file.path, file.category)))
    present = {file.category for file in files}
    categories_found = tuple(category for category in CATEGORIES if category in present)
    categories_missing = tuple(
        category for category in _REPORTED_MISSING if category not in present
    )

    return SourceTruthDiscovery(
        repo_path=repo_path,
        files=files,
        categories_found=categories_found,
        categories_missing=categories_missing,
        conflict_hints=_conflict_hints(files),
    )
