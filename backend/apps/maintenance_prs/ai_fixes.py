"""Category-agnostic AI code-fix author.

Given an approved MaintenancePRPlan + the opportunity it came from, ask the LLM
to produce the minimal fix for one source file and validate the result before it
is committed. Tier / confidence / protected-path gating happens upstream
(planner + executor `_guard_executable`); this module only authors + validates.
"""

from __future__ import annotations

import ast
import difflib
import logging
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from apps.common.llm import LLMError, complete
from apps.maintenance_prs.models import MaintenancePRPlan

logger = logging.getLogger("gardener.ai_fixes")

# Progress callback: (percent: int 0-100, phase: str, message: str).
ProgressCallback = Callable[[int, str, str], None]


def _report(progress: ProgressCallback | None, percent: int, phase: str, message: str) -> None:
    logger.info("ai_fix %3d%% [%s] %s", percent, phase, message)
    if progress is not None:
        try:
            progress(percent, phase, message)
        except Exception:  # noqa: BLE001 - progress reporting must never break the fix
            logger.warning("ai_fix.progress_callback_failed", exc_info=True)


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
    {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".rb"}
)

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

_MAX_CHANGE_RATIO = 0.6
_SINGLE_PASS_CHARS = 40_000
_CHUNK_CHARS = 32_000
_MAX_CHUNKS = 40
_MAX_FILE_CHARS = _CHUNK_CHARS * _MAX_CHUNKS
_DEFAULT_CHUNK_WORKERS = 8
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
    progress: ProgressCallback | None = None,
) -> str:
    """Return the LLM-edited file content, validated. Raises AIFixError on failure."""

    opportunity = opportunity or {}
    if len(content) > _MAX_FILE_CHARS:
        raise AIFixError(
            f"{path} is too large ({len(content)} chars) even for chunked AI editing."
        )

    chunks = [content] if len(content) <= _SINGLE_PASS_CHARS else _chunk_content(path, content)
    total = len(chunks)
    _report(progress, 0, "reading", f"{path}: reading in {total} part(s)")

    blocks: list[tuple[str, str]] = []
    whole_file_fallback: str | None = None
    outputs = _complete_chunks(path, chunks, plan, opportunity, progress=progress)
    for raw in outputs:
        chunk_blocks = _parse_edit_blocks(raw)
        if chunk_blocks:
            blocks.extend(chunk_blocks)
            continue
        if total == 1:
            fenced = _FENCE_RE.search(raw)
            if fenced:
                whole_file_fallback = fenced.group(1).strip("\n") + "\n"

    _report(progress, 90, "applying", f"{path}: applying {len(blocks)} edit(s)")
    if blocks:
        blocks = list(dict.fromkeys(blocks))
        updated = _apply_edit_blocks(path, content, blocks)
    elif whole_file_fallback is not None:
        updated = whole_file_fallback
    else:
        raise AIFixError(f"AI fix for {path} produced no applicable edits.")

    _validate(path, content, updated, plan.category)
    _report(progress, 100, "done", f"{path}: fix ready")
    return updated


def _complete_chunks(
    path: str,
    chunks: list[str],
    plan: MaintenancePRPlan,
    opportunity: dict,
    progress: ProgressCallback | None = None,
) -> list[str]:
    total = len(chunks)
    if total == 1:
        raw = _complete_chunk(path, chunks[0], plan, opportunity, part=(1, 1))
        _report(progress, 90, "analyzing", f"{path}: part 1/1")
        return [raw]

    workers = min(_chunk_worker_count(), total)
    outputs: dict[int, str] = {}
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _complete_chunk,
                path,
                chunk,
                plan,
                opportunity,
                (index + 1, total),
            ): index
            for index, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            index = futures[future]
            outputs[index] = future.result()
            completed += 1
            percent = int(completed / total * 90)
            blocks_so_far = sum(
                len(_parse_edit_blocks(output)) for output in outputs.values()
            )
            _report(
                progress,
                percent,
                "analyzing",
                f"{path}: part {index + 1}/{total}, {blocks_so_far} edit(s) so far",
            )

    return [outputs[index] for index in range(total)]


def _complete_chunk(
    path: str,
    content: str,
    plan: MaintenancePRPlan,
    opportunity: dict,
    part: tuple[int, int],
) -> str:
    prompt = _build_prompt(path, content, plan, opportunity, part=part)
    try:
        return complete(prompt, system=_SYSTEM_PROMPT, max_tokens=_MODEL_OUTPUT_TOKEN_CAP)
    except LLMError as exc:
        raise AIFixError(f"LLM fix failed for {path}: {exc}") from exc


def _chunk_worker_count() -> int:
    raw = os.getenv("GARDENER_AI_FIX_CHUNK_WORKERS") or os.getenv(
        "GARDENER_AI_FIX_WORKERS",
        str(_DEFAULT_CHUNK_WORKERS),
    )
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_CHUNK_WORKERS
    return max(1, min(value, _DEFAULT_CHUNK_WORKERS))


def _chunk_content(path: str, content: str) -> list[str]:
    boundaries = _python_top_level_line_starts(content) if path.endswith(".py") else None
    lines = content.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    size = 0

    def flush():
        nonlocal current, size
        if current:
            chunks.append("\n".join(current))
            current = []
            size = 0

    for lineno, line in enumerate(lines, start=1):
        at_boundary = boundaries is not None and lineno in boundaries
        if size + len(line) + 1 > _CHUNK_CHARS and current and (
            boundaries is None or at_boundary
        ):
            flush()
        current.append(line)
        size += len(line) + 1
    flush()

    if len(chunks) > _MAX_CHUNKS:
        raise AIFixError(
            f"{path} needs {len(chunks)} chunks (> {_MAX_CHUNKS}); refused."
        )
    return chunks


def _python_top_level_line_starts(content: str) -> set[int] | None:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    return {node.lineno for node in tree.body if hasattr(node, "lineno")}


_SYSTEM_PROMPT = (
    "You are a careful senior engineer making minimal, safe maintenance edits. "
    "Return ONLY SEARCH/REPLACE edit blocks, no prose. Each block:\n"
    "<<<<<<< SEARCH\n<exact lines copied verbatim from the file>\n=======\n"
    "<replacement lines>\n>>>>>>> REPLACE\n"
    "The SEARCH text must match the current file exactly (including indentation). "
    "Use as few, as small blocks as possible. To delete code, leave the REPLACE side empty."
)


def _build_prompt(
    path: str,
    content: str,
    plan: MaintenancePRPlan,
    opportunity: dict,
    part: tuple[int, int] = (1, 1),
) -> str:
    guidance = _CATEGORY_GUIDANCE.get(plan.category, "Apply the smallest safe fix for the finding.")
    summary = opportunity.get("summary") or plan.title
    evidence = opportunity.get("evidence") or []
    evidence_lines = "\n".join(
        f"- {e.get('path', path)}: {e.get('summary', '')}"
        for e in evidence
        if isinstance(e, dict)
    ) or "- (no extra evidence)"
    index, total = part
    if total > 1:
        scope = (
            f"This is part {index} of {total} of a large file. Only propose edits "
            "for code shown in THIS part; SEARCH text must be copied from it. If "
            "nothing here needs changing, return no blocks.\n"
        )
        label = f"File part {index}/{total}"
    else:
        scope = ""
        label = "Current file content"
    return (
        f"Category: {plan.category}\n"
        f"File: {path}\n"
        f"Finding: {summary}\n"
        f"Evidence:\n{evidence_lines}\n\n"
        f"Instruction: {guidance}\n"
        f"{scope}"
        "Respond with SEARCH/REPLACE edit blocks only; do not return the whole file.\n\n"
        f"{label}:\n```\n{content}\n```"
    )


_EDIT_BLOCK_RE = re.compile(
    r"<{5,}[ \t]*SEARCH[ \t]*\n(.*?)={5,}[^\n]*\n(.*?)>{5,}[ \t]*REPLACE",
    re.DOTALL,
)


def _parse_edit_blocks(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _EDIT_BLOCK_RE.finditer(text)]


def _apply_edit_blocks(path: str, content: str, blocks: list[tuple[str, str]]) -> str:
    updated = content
    applied = 0
    skipped = 0
    for search, replace in blocks:
        if not search.strip():
            skipped += 1
            continue

        matched = search if search in updated else _match_ignoring_trailing_ws(updated, search)
        if matched is None:
            skipped += 1
            continue

        candidate = updated.replace(matched, replace, 1)
        if path.endswith(".py") and not _python_parses(candidate):
            skipped += 1
            continue

        updated = candidate
        applied += 1

    if applied == 0:
        raise AIFixError(
            f"AI fix for {path}: no SEARCH block matched the file ({skipped} skipped)."
        )
    if skipped:
        logger.info("ai_fix %s: applied %d edit(s), skipped %d", path, applied, skipped)
    return updated


def _python_parses(content: str) -> bool:
    try:
        ast.parse(content)
    except SyntaxError:
        return False
    return True


def _match_ignoring_trailing_ws(content: str, search: str) -> str | None:
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
