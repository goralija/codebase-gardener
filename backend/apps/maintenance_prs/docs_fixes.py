from __future__ import annotations

from apps.maintenance_prs.models import MaintenancePRPlan

NOTE_HEADING = "## Gardener maintenance note"


def docs_actual_fix_paths(plan: MaintenancePRPlan) -> list[str]:
    if plan.category != "docs":
        return []

    paths: list[str] = []
    for path in plan.changed_paths or []:
        if not isinstance(path, str):
            continue
        if not _is_safe_markdown_path(path):
            continue
        paths.append(path)
    return paths


def has_docs_actual_fix(plan: MaintenancePRPlan) -> bool:
    return bool(docs_actual_fix_paths(plan))


def apply_docs_maintenance_note(content: str, plan: MaintenancePRPlan) -> str:
    block = _maintenance_note_block(plan)
    start = _start_marker(plan)
    end = _end_marker(plan)
    start_index = content.find(start)
    if start_index >= 0:
        end_index = content.find(end, start_index)
        if end_index >= 0:
            end_index += len(end)
            prefix = content[:start_index].rstrip()
            suffix = content[end_index:].lstrip("\n")
            return _join_note_parts(prefix, block, suffix)

    if content.strip():
        return f"{content.rstrip()}\n\n{block}\n"
    return f"{block}\n"


def _maintenance_note_block(plan: MaintenancePRPlan) -> str:
    sections = plan.pr_body_sections or {}
    lines = [
        _start_marker(plan),
        NOTE_HEADING,
        "",
        f"Gardener opened this maintenance PR from plan `{plan.id}`.",
        "",
        f"- Goal: {_section(sections, 'goal')}",
        f"- Evidence: {_section(sections, 'evidence')}",
        f"- Entropy impact: {_section(sections, 'entropy_impact')}",
        f"- Verification: {_section(sections, 'verification')}",
        _end_marker(plan),
    ]
    return "\n".join(lines)


def _section(sections: dict, key: str) -> str:
    value = sections.get(key)
    if not isinstance(value, str) or not value.strip():
        return "Not supplied."
    return " ".join(value.split())


def _join_note_parts(prefix: str, block: str, suffix: str) -> str:
    parts = [part for part in [prefix, block, suffix.rstrip()] if part]
    return "\n\n".join(parts) + "\n"


def _start_marker(plan: MaintenancePRPlan) -> str:
    return f"<!-- gardener-maintenance-note:start {plan.id} -->"


def _end_marker(plan: MaintenancePRPlan) -> str:
    return f"<!-- gardener-maintenance-note:end {plan.id} -->"


def _is_safe_markdown_path(path: str) -> bool:
    if not path.lower().endswith(".md"):
        return False
    if path.startswith("/") or any(part in {"", ".", ".."} for part in path.split("/")):
        return False
    return not any(char in path for char in "*?[]")
