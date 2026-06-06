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

# Largest file we attempt whole-file editing on (chars). Bigger files are skipped
# cleanly; they need the diff-based author (follow-up) to be handled safely.
_MAX_FILE_CHARS = 48_000

# Upper bound on requested completion tokens (model output ceiling headroom).
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
    """Return the LLM-edited file content, validated. Raises AIFixError on failure."""
    if len(content) > _MAX_FILE_CHARS:
        raise AIFixError(
            f"{path} is too large ({len(content)} chars) for whole-file AI editing; "
            "skipped."
        )

    prompt = _build_prompt(path, content, plan, opportunity or {})
    # Allow the full file back: budget output tokens from the file size
    # (~4 chars/token) plus headroom, capped at the model's output ceiling.
    max_tokens = min(_MODEL_OUTPUT_TOKEN_CAP, len(content) // 3 + 1024)
    try:
        raw = complete(prompt, system=_SYSTEM_PROMPT, max_tokens=max_tokens)
    except LLMError as exc:
        raise AIFixError(f"LLM fix failed for {path}: {exc}") from exc

    updated = _extract_code(raw)
    _validate(path, content, updated, plan.category)
    return updated


_SYSTEM_PROMPT = (
    "You are a careful senior engineer making one minimal, safe maintenance edit. "
    "Return ONLY the complete updated file inside a single fenced code block, with no "
    "explanation before or after."
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
        "Preserve formatting and unrelated code. Return the FULL updated file.\n\n"
        f"Current file content:\n```\n{content}\n```"
    )


def _extract_code(text: str) -> str:
    match = _FENCE_RE.search(text)
    code = match.group(1) if match else text
    return code.strip("\n") + "\n"


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
