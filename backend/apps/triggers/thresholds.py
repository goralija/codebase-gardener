"""Constitution-aware thresholds for commit-count and risky-module triggers.

Values come from the Repository Constitution when available and fall back to
conservative defaults derived from ``docs/09-autonomy-and-automation-rules.md``
(Tier 3 advisory areas) when a constitution is not yet wired for a repository.
"""

from __future__ import annotations

from collections.abc import Iterable
from fnmatch import fnmatch

DEFAULT_COMMIT_THRESHOLD = 10

# Tier 3 advisory areas (docs/09) used when the constitution defines no
# protected modules or never-touch rules.
DEFAULT_PROTECTED_SEGMENTS = (
    "auth",
    "payments",
    "pricing",
    "permissions",
    "migrations",
    "security",
)

_COMMIT_THRESHOLD_KEYS = (
    "commit_session_threshold",
    "session_commit_threshold",
    "n_commits_threshold",
)


def commit_threshold(constitution: dict | None) -> int:
    """Return the commit count that should trigger a session."""

    constitution = constitution or {}
    risk_policies = constitution.get("risk_policies")
    sources: list[dict] = []
    if isinstance(risk_policies, dict):
        sources.append(risk_policies)
    sources.append(constitution)

    for source in sources:
        for key in _COMMIT_THRESHOLD_KEYS:
            value = source.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
    return DEFAULT_COMMIT_THRESHOLD


def changed_paths_hit_protected(
    paths: Iterable[str],
    constitution: dict | None,
) -> str | None:
    """Return a reason string if any changed path touches a protected area."""

    constitution = constitution or {}
    paths = [str(path) for path in paths if path]

    protected_modules = constitution.get("protected_modules") or []
    never_touch = constitution.get("never_touch") or []

    for path in paths:
        for rule in never_touch:
            pattern = rule.get("path", "") if isinstance(rule, dict) else ""
            if pattern and fnmatch(path, pattern):
                reason = rule.get("reason", "no reason given") if isinstance(rule, dict) else ""
                return f"{path} matches never-touch rule: {reason}"
        for module in protected_modules:
            if not isinstance(module, dict):
                continue
            for pattern in module.get("paths", []) or []:
                if pattern and fnmatch(path, pattern):
                    return (
                        f"{path} matches protected module "
                        f"{module.get('name', 'unknown')}"
                    )

    if protected_modules or never_touch:
        return None

    # Fallback: only applied when the constitution defines no protected areas.
    for path in paths:
        segments = {segment for segment in path.replace("\\", "/").split("/") if segment}
        hit = segments.intersection(DEFAULT_PROTECTED_SEGMENTS)
        if hit:
            return f"{path} touches default protected area: {sorted(hit)[0]}"
    return None
