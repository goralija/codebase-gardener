"""Category-agnostic AI code-fix author.

Given an approved MaintenancePRPlan + the opportunity it came from, ask the LLM
to produce the minimal fix for one source file and validate the result before it
is committed. Tier / confidence / protected-path gating happens upstream
(planner + executor `_guard_executable`); this module only authors + validates.
"""

from __future__ import annotations

import ast
import difflib
import re

from apps.common.llm import LLMError, complete
from apps.maintenance_prs.models import MaintenancePRPlan


# Categories an AI author can attempt (docs has its own deterministic author).
SUPPORTED_AI_CATEGORIES = frozenset(
    {
        "dead_code",
        "complexity_reduction",
        "refactoring",
        "layer_violation_repair",
        "tests",
    }
)

_SOURCE_EXTENSIONS = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb"}
)

# Per-category instruction appended to the prompt.
_CATEGORY_GUIDANCE = {
    "dead_code": (
        "Remove only the unused/dead code identified by the finding. Do not change "
        "any behavior that is still reachable. Keep imports consistent."
    ),
    "complexity_reduction": (
        "Refactor to reduce complexity without changing observable behavior or the "
        "public API. Prefer small, local extractions."
    ),
    "refactoring": (
        "Apply a safe, behavior-preserving refactor addressing the finding. Do not "
        "change the public API."
    ),
    "layer_violation_repair": (
        "Repair the layering/boundary violation with the smallest change that keeps "
        "behavior intact."
    ),
    "tests": (
        "Add focused tests covering the untested behavior in this file. Do not modify "
        "production code."
    ),
}

# Reject whole-file rewrites: fraction of lines allowed to change (except tests).
_MAX_CHANGE_RATIO = 0.6

# Largest file we send for AI editing (chars). Edit blocks keep the OUTPUT small
# regardless of size; this bounds the INPUT so it fits the model context. Files
# beyond this are skipped cleanly (would need chunking).
_MAX_FILE_CHARS = 200_000

# Upper bound on requested completion tokens. Edit blocks are small, so this is
# headroom, not sized to the file.
_MODEL_OUTPUT_TOKEN_CAP = 16_000

_FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)


class AIFixError(RuntimeError):
    """Raised when the AI fix is missing, malformed, or fails validation."""


def has_ai_fix(plan: MaintenancePRPlan) -> bool:
    return plan.category in SUPPORTED_AI_CATEGORIES and bool(ai_fixable_paths(plan))


def ai_fixable_paths(plan: MaintenancePRPlan) -> list[str]:
    if plan.category not in SUPPORTED_AI_CATEGORIES:
        return []
    return [
        path
        for path in (plan.changed_paths or [])
        if isinstance(path, str) and _is_safe_source_path(path)
    ]


def apply_ai_fix(
    path: str,
    content: str,
    plan: MaintenancePRPlan,
    opportunity: dict | None = None,
) -> str:
    """Return the LLM-edited file content, validated. Raises AIFixError on failure.

    Uses SEARCH/REPLACE edit blocks: the model returns only the changed regions,
    so output stays small and the approach scales to large files. Falls back to a
    whole-file fenced block if the model returns one instead.
    """
    if len(content) > _MAX_FILE_CHARS:
        raise AIFixError(
            f"{path} is too large ({len(content)} chars) for AI editing; skipped."
        )

    prompt = _build_prompt(path, content, plan, opportunity or {})
    try:
        raw = complete(prompt, system=_SYSTEM_PROMPT, max_tokens=_MODEL_OUTPUT_TOKEN_CAP)
    except LLMError as exc:
        raise AIFixError(f"LLM fix failed for {path}: {exc}") from exc

    blocks = _parse_edit_blocks(raw)
    if blocks:
        updated = _apply_edit_blocks(path, content, blocks)
    else:
        # Fallback: model returned the whole file in a fenced block.
        fenced = _FENCE_RE.search(raw)
        if not fenced:
            raise AIFixError(f"AI fix for {path} returned no edit blocks or file.")
        updated = fenced.group(1).strip("\n") + "\n"

    _validate(path, content, updated, plan.category)
    return updated


_SYSTEM_PROMPT = (
    "You are a careful senior engineer making minimal, safe maintenance edits. "
    "Return ONLY SEARCH/REPLACE edit blocks, no prose. Each block:\n"
    "<<<<<<< SEARCH\n<exact lines copied verbatim from the file>\n=======\n"
    "<replacement lines>\n>>>>>>> REPLACE\n"
    "The SEARCH text must match the current file exactly (including indentation). "
    "Use as few, as small blocks as possible. To delete code, leave the REPLACE side empty."
)


def _build_prompt(path: str, content: str, plan: MaintenancePRPlan, opportunity: dict) -> str:
    guidance = _CATEGORY_GUIDANCE.get(plan.category, "Apply the smallest safe fix for the finding.")
    summary = opportunity.get("summary") or plan.title
    evidence = opportunity.get("evidence") or []
    evidence_lines = "\n".join(
        f"- {e.get('path', path)}: {e.get('summary', '')}"
        for e in evidence
        if isinstance(e, dict)
    ) or "- (no extra evidence)"
    return (
        f"Category: {plan.category}\n"
        f"File: {path}\n"
        f"Finding: {summary}\n"
        f"Evidence:\n{evidence_lines}\n\n"
        f"Instruction: {guidance}\n"
        "Respond with SEARCH/REPLACE edit blocks only; do not return the whole file.\n\n"
        f"Current file content:\n```\n{content}\n```"
    )


_EDIT_BLOCK_RE = re.compile(
    r"<{5,}[ \t]*SEARCH[ \t]*\n(.*?)={5,}[^\n]*\n(.*?)>{5,}[ \t]*REPLACE",
    re.DOTALL,
)


def _parse_edit_blocks(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _EDIT_BLOCK_RE.finditer(text)]


def _apply_edit_blocks(path: str, content: str, blocks: list[tuple[str, str]]) -> str:
    updated = content
    for search, replace in blocks:
        if not search.strip():
            raise AIFixError(f"AI fix for {path} had an empty SEARCH block.")
        if search in updated:
            updated = updated.replace(search, replace, 1)
            continue
        # Tolerate trailing-whitespace / line-ending differences.
        normalized = _match_ignoring_trailing_ws(updated, search)
        if normalized is None:
            raise AIFixError(
                f"AI fix for {path}: a SEARCH block did not match the file exactly."
            )
        updated = updated.replace(normalized, replace, 1)
    return updated


def _match_ignoring_trailing_ws(content: str, search: str) -> str | None:
    """Return the substring of *content* matching *search* ignoring trailing
    whitespace per line, or None if not found."""
    search_lines = [line.rstrip() for line in search.split("\n")]
    content_lines = content.split("\n")
    n = len(search_lines)
    for i in range(len(content_lines) - n + 1):
        window = content_lines[i : i + n]
        if [line.rstrip() for line in window] == search_lines:
            return "\n".join(window)
    return None


def _validate(path: str, original: str, updated: str, category: str) -> None:
    if not updated.strip():
        raise AIFixError(f"AI fix for {path} was empty.")
    if updated.strip() == original.strip():
        raise AIFixError(f"AI fix for {path} made no change.")

    if path.endswith(".py"):
        try:
            ast.parse(updated)
        except SyntaxError as exc:
            raise AIFixError(f"AI fix for {path} is not valid Python: {exc}") from exc

    if category != "tests":
        ratio = _change_ratio(original, updated)
        if ratio > _MAX_CHANGE_RATIO:
            raise AIFixError(
                f"AI fix for {path} rewrote {ratio:.0%} of the file; rejected as unsafe."
            )


def _change_ratio(original: str, updated: str) -> float:
    old = original.splitlines()
    new = updated.splitlines()
    if not old:
        return 1.0
    sm = difflib.SequenceMatcher(a=old, b=new)
    changed = sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in sm.get_opcodes()
        if tag != "equal"
    )
    return changed / max(len(old), len(new), 1)


def _is_safe_source_path(path: str) -> bool:
    if not any(path.endswith(ext) for ext in _SOURCE_EXTENSIONS):
        return False
    if path.startswith("/") or any(part in {"", ".", ".."} for part in path.split("/")):
        return False
    return not any(char in path for char in "*?[]")
