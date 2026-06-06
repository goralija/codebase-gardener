from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .discovery import SourceTruthDiscovery, SourceTruthFile, discover_source_truth


JsonObject = dict[str, Any]

_BACKTICK = re.compile(r"`([^`]+)`")

# Section header (case-insensitive) -> internal key.
_SECTION_ALIASES: dict[str, str] = {
    "product purpose": "purpose",
    "architecture boundaries": "architecture",
    "protected modules": "protected",
    "never-touch paths": "never_touch",
    "never touch paths": "never_touch",
    "autonomous fixes allowed": "autonomous",
    "assisted-only fixes": "assisted",
    "assisted fixes allowed": "assisted",
    "advisory-only areas": "advisory",
    "advisory only areas": "advisory",
    "ignored paths": "ignored",
    "test rules": "test_rules",
}

# Canonical categories used for completeness scoring.
_COMPLETENESS_CATEGORIES = (
    "protected_modules",
    "never_touch",
    "allowed_fixes",
    "architecture_boundaries",
    "ignored_paths",
)

# Keyword -> fix-category slug. First match wins, longest keys first.
_FIX_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("dead code removal", "dead_code"),
    ("dead-code removal", "dead_code"),
    ("dead code", "dead_code"),
    ("dead-code", "dead_code"),
    ("documentation", "docs"),
    ("doc", "docs"),
    ("lint", "lint_format"),
    ("format", "lint_format"),
    ("test", "tests"),
    ("refactor", "refactoring"),
    ("dependency", "dependency_patch"),
    ("payment", "payments"),
    ("billing", "payments"),
    ("pricing", "pricing"),
    ("permission", "permissions"),
    ("auth", "auth"),
    ("security", "security_sensitive_code"),
    ("api", "api_behavior"),
)


def build_repository_constitution(
    repo_path: Path,
    repository_id: str,
    commit_sha: str,
    discovery: SourceTruthDiscovery | None = None,
) -> JsonObject:
    repo_path = repo_path.resolve()
    discovery = discovery or discover_source_truth(repo_path)

    gardener = _find_file(discovery, "constitution")
    sections = _parse_sections(repo_path, gardener)

    architecture_conflict = _genuine_architecture_conflict(
        repo_path, discovery, sections
    )

    protected_modules = _protected_modules(sections.get("protected", []), gardener)
    never_touch = _never_touch(sections.get("never_touch", []), gardener)
    allowed_fixes = {
        "autonomous": _fix_categories(sections.get("autonomous", [])),
        "assisted": _fix_categories(sections.get("assisted", [])),
        "advisory": _fix_categories(sections.get("advisory", [])),
    }
    # Q2: on architecture conflict, do NOT auto-emit boundary rules; surface a question instead.
    architecture_boundaries = (
        []
        if architecture_conflict
        else _architecture_boundaries(sections.get("architecture", []), gardener)
    )
    ignored_paths = _ignored_paths(sections.get("ignored", []))

    open_questions = _open_questions(
        gardener=gardener,
        architecture_conflict=architecture_conflict,
        protected_modules=protected_modules,
        never_touch=never_touch,
        allowed_fixes=allowed_fixes,
        architecture_boundaries=architecture_boundaries,
        ignored_paths=ignored_paths,
    )

    completeness_score = _completeness_score(
        protected_modules=protected_modules,
        never_touch=never_touch,
        allowed_fixes=allowed_fixes,
        architecture_boundaries=architecture_boundaries,
        ignored_paths=ignored_paths,
    )

    return {
        "schema_version": "1.0",
        "repository_id": repository_id,
        "commit_sha": commit_sha,
        "completeness_score": completeness_score,
        "protected_modules": protected_modules,
        "never_touch": never_touch,
        "allowed_fixes": allowed_fixes,
        "architecture_boundaries": architecture_boundaries,
        "ignored_paths": ignored_paths,
        "open_questions": open_questions,
    }


_RESTRICTIVE = re.compile(r"must not|cannot|can't|forbidden|not\s+\w*\s*imports?")
_PERMISSIVE = re.compile(r"\bmay\b|\ballowed\b|can import")
_SUBJECT_WORDS = ("persistence", "models", "model", "database")


def _genuine_architecture_conflict(
    repo_path: Path,
    discovery: SourceTruthDiscovery,
    sections: dict[str, list[str]],
) -> bool:
    """Real disagreement (not mere co-existence): a permissive import claim in one
    source and a restrictive claim in another that share a subject (path or keyword).
    """
    arch_file = _find_file(discovery, "architecture")
    gardener_arch = " ".join(sections.get("architecture", []))
    if arch_file is None or not gardener_arch.strip():
        return False

    arch_text = (repo_path / arch_file.path).read_text(encoding="utf-8")
    claims = _import_claims(gardener_arch) + _import_claims(arch_text)

    permissive = [subjects for polarity, subjects in claims if polarity == "permissive"]
    restrictive = [subjects for polarity, subjects in claims if polarity == "restrictive"]
    return any(p & r for p in permissive for r in restrictive)


def _import_claims(text: str) -> list[tuple[str, set[str]]]:
    claims: list[tuple[str, set[str]]] = []
    for sentence in re.split(r"[.\n]", text):
        lowered = sentence.lower()
        if "import" not in lowered:
            continue
        if _RESTRICTIVE.search(lowered):
            polarity = "restrictive"
        elif _PERMISSIVE.search(lowered):
            polarity = "permissive"
        else:
            continue
        subjects = set(_globs(sentence))
        subjects.update(word for word in _SUBJECT_WORDS if word in lowered)
        if subjects:
            claims.append((polarity, subjects))
    return claims


def _find_file(discovery: SourceTruthDiscovery, category: str) -> SourceTruthFile | None:
    for file in discovery.files:
        if file.category == category:
            return file
    return None


def _parse_sections(
    repo_path: Path, gardener: SourceTruthFile | None
) -> dict[str, list[str]]:
    if gardener is None:
        return {}
    text = (repo_path / gardener.path).read_text(encoding="utf-8")

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            header = line[3:].strip().lower()
            current = _SECTION_ALIASES.get(header)
            if current is not None:
                sections.setdefault(current, [])
            continue
        if current is None:
            continue
        if line.startswith("- "):
            sections[current].append(line[2:].strip())
        elif line and not line.startswith("#"):
            # Capture non-bullet prose (e.g. "Test Rules" single sentence sections).
            sections[current].append(line)
    return sections


def _globs(text: str) -> list[str]:
    return _BACKTICK.findall(text)


def _evidence(gardener: SourceTruthFile | None, section: str) -> list[JsonObject]:
    if gardener is None:
        return []
    ref = gardener.to_evidence()
    ref["section"] = section
    return [ref]


def _protected_modules(
    bullets: list[str], gardener: SourceTruthFile | None
) -> list[JsonObject]:
    modules: list[JsonObject] = []
    for bullet in bullets:
        paths = _globs(bullet)
        if not paths:
            continue
        label = bullet.split(":", 1)[0].strip() if ":" in bullet else bullet.strip()
        label = _BACKTICK.sub("", label).strip(" .-")
        modules.append(
            {
                "name": label or "module",
                "paths": paths,
                "reason": _reason(bullet),
            }
        )
    return modules


def _never_touch(
    bullets: list[str], gardener: SourceTruthFile | None
) -> list[JsonObject]:
    entries: list[JsonObject] = []
    for bullet in bullets:
        paths = _globs(bullet)
        if not paths:
            continue
        reason = _reason(bullet) or "Declared never-touch."
        for path in paths:
            entries.append({"path": path, "reason": reason})
    return entries


def _architecture_boundaries(
    bullets: list[str], gardener: SourceTruthFile | None
) -> list[JsonObject]:
    rules: list[JsonObject] = []
    for index, bullet in enumerate(bullets, start=1):
        if not bullet:
            continue
        globs = _globs(bullet)
        rules.append(
            {
                "rule_id": f"arch_{index:03d}",
                "description": _BACKTICK.sub(lambda m: m.group(1), bullet).strip(),
                "forbidden_from": globs[:1],
                "forbidden_to": globs[1:2],
                "evidence": _evidence(gardener, "Architecture Boundaries"),
            }
        )
    return rules


def _ignored_paths(bullets: list[str]) -> list[str]:
    paths: list[str] = []
    for bullet in bullets:
        for glob in _globs(bullet):
            if glob not in paths:
                paths.append(glob)
    return paths


def _fix_categories(bullets: list[str]) -> list[str]:
    categories: list[str] = []
    for bullet in bullets:
        slug = _fix_slug(bullet)
        if slug and slug not in categories:
            categories.append(slug)
    return categories


def _fix_slug(text: str) -> str:
    lowered = text.lower()
    for keyword, slug in _FIX_KEYWORDS:
        if keyword in lowered:
            return slug
    return _slugify(text)


def _slugify(text: str) -> str:
    cleaned = _BACKTICK.sub("", text)
    slug = re.sub(r"[^a-z0-9]+", "_", cleaned.lower()).strip("_")
    # Keep slugs short and stable.
    return "_".join(slug.split("_")[:3])


def _reason(bullet: str) -> str:
    match = re.search(r"\bbecause\b\s*(.+)", bullet, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(".") + "."
    return ""


def _completeness_score(
    *,
    protected_modules: list[JsonObject],
    never_touch: list[JsonObject],
    allowed_fixes: JsonObject,
    architecture_boundaries: list[JsonObject],
    ignored_paths: list[str],
) -> float:
    populated = {
        "protected_modules": bool(protected_modules),
        "never_touch": bool(never_touch),
        "allowed_fixes": any(allowed_fixes.values()),
        "architecture_boundaries": bool(architecture_boundaries),
        "ignored_paths": bool(ignored_paths),
    }
    score = sum(populated[name] for name in _COMPLETENESS_CATEGORIES) / len(
        _COMPLETENESS_CATEGORIES
    )
    return round(score, 2)


def _open_questions(
    *,
    gardener: SourceTruthFile | None,
    architecture_conflict: bool,
    protected_modules: list[JsonObject],
    never_touch: list[JsonObject],
    allowed_fixes: JsonObject,
    architecture_boundaries: list[JsonObject],
    ignored_paths: list[str],
) -> list[JsonObject]:
    questions: list[JsonObject] = []

    def add(severity: str, question: str, evidence: list[JsonObject] | None = None) -> None:
        questions.append(
            {
                "question_id": f"q_{len(questions) + 1:03d}",
                "severity": severity,
                "question": question,
                "evidence": evidence or [],
            }
        )

    if gardener is None:
        add(
            "blocking",
            "No repository constitution (GARDENER.md) found; cannot derive rules.",
        )
        return questions

    if architecture_conflict:
        add(
            "blocking",
            "Architecture source truth disagrees between GARDENER.md and "
            "ARCHITECTURE.md; which one governs?",
            _evidence(gardener, "Architecture Boundaries"),
        )

    populated = {
        "protected_modules": bool(protected_modules),
        "never_touch": bool(never_touch),
        "allowed_fixes": any(allowed_fixes.values()),
        "architecture_boundaries": bool(architecture_boundaries),
        "ignored_paths": bool(ignored_paths),
    }
    for name in _COMPLETENESS_CATEGORIES:
        if name == "architecture_boundaries" and architecture_conflict:
            continue
        if not populated[name]:
            add("non_blocking", f"No {name.replace('_', ' ')} declared in source truth.")

    return questions
