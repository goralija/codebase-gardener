import pytest

from apps.maintenance_prs import ai_fixes
from apps.maintenance_prs.ai_fixes import AIFixError, apply_ai_fix


class _Plan:
    """Lightweight stand-in for MaintenancePRPlan (no DB needed)."""

    def __init__(self, category="dead_code", changed_paths=None, title="Remove dead code"):
        self.category = category
        self.changed_paths = changed_paths if changed_paths is not None else ["core/util.py"]
        self.title = title


def _patch_llm(monkeypatch, response: str):
    monkeypatch.setattr(ai_fixes, "complete", lambda *a, **k: response)


ORIGINAL = "import os\n\n\ndef used():\n    return 1\n\n\ndef dead():\n    return 2\n"


def test_apply_ai_fix_returns_validated_reduced_file(monkeypatch):
    fixed = "import os\n\n\ndef used():\n    return 1\n"
    _patch_llm(monkeypatch, f"```python\n{fixed}```")

    result = apply_ai_fix("core/util.py", ORIGINAL, _Plan(), {"summary": "dead()"})

    assert "def dead()" not in result
    assert "def used()" in result


def test_apply_ai_fix_applies_search_replace_block(monkeypatch):
    block = (
        "<<<<<<< SEARCH\n"
        "def dead():\n    return 2\n"
        "=======\n"
        ">>>>>>> REPLACE\n"
    )
    _patch_llm(monkeypatch, f"Here is the edit:\n{block}")

    result = apply_ai_fix("core/util.py", ORIGINAL, _Plan(), {"summary": "dead()"})

    assert "def dead()" not in result
    assert "def used()" in result


<<<<<<< HEAD
<<<<<<< HEAD
def test_apply_ai_fix_chunks_large_file_and_applies_edits(monkeypatch):
    from apps.maintenance_prs import ai_fixes

    # Build a >40k-char file so it is processed in multiple chunk passes.
=======
def test_apply_ai_fix_chunks_large_file_and_applies_edits(monkeypatch):
    from apps.maintenance_prs import ai_fixes

    # Build a >40k-char file so it is processed in multiple chunks.
>>>>>>> 8135096 (feat(ai-fixes): chunked reading so large files are edited, not skipped)
    kept = "".join(f"def used_{i}():\n    return {i}\n\n\n" for i in range(4000))
    big = kept + "def dead():\n    return 0\n"
    assert len(big) > 40_000

    calls = {"n": 0}

    def fake_complete(*a, **k):
        calls["n"] += 1
        return (
            "<<<<<<< SEARCH\ndef dead():\n    return 0\n=======\n>>>>>>> REPLACE\n"
        )

<<<<<<< HEAD
    monkeypatch.setenv("GARDENER_AI_FIX_CHUNK_WORKERS", "4")
=======
>>>>>>> 8135096 (feat(ai-fixes): chunked reading so large files are edited, not skipped)
    monkeypatch.setattr(ai_fixes, "complete", fake_complete)

    result = apply_ai_fix("core/big.py", big, _Plan(changed_paths=["core/big.py"]), {})

<<<<<<< HEAD
    assert calls["n"] > 1
=======
    assert calls["n"] > 1          # multiple chunk passes
>>>>>>> 8135096 (feat(ai-fixes): chunked reading so large files are edited, not skipped)
    assert "def dead()" not in result
    assert "def used_0()" in result


<<<<<<< HEAD
=======
>>>>>>> c88ee3e (feat(ai-fixes): SEARCH/REPLACE edit blocks for any-size files)
=======
>>>>>>> 8135096 (feat(ai-fixes): chunked reading so large files are edited, not skipped)
def test_apply_ai_fix_rejects_unmatched_search_block(monkeypatch):
    block = (
        "<<<<<<< SEARCH\n"
        "def not_in_file():\n    return 9\n"
        "=======\n"
        "def replaced():\n    return 9\n"
        ">>>>>>> REPLACE\n"
    )
    _patch_llm(monkeypatch, block)

    with pytest.raises(AIFixError):
        apply_ai_fix("core/util.py", ORIGINAL, _Plan(), {})


<<<<<<< HEAD
def test_apply_ai_fix_skips_invalid_python_block_but_keeps_valid_edit(monkeypatch):
    bad_block = (
        "<<<<<<< SEARCH\n"
        "def used():\n    return 1\n"
        "=======\n"
        "def used():\n    return {\n"
        ">>>>>>> REPLACE\n"
    )
    good_block = (
        "<<<<<<< SEARCH\n"
        "def dead():\n    return 2\n"
        "=======\n"
        ">>>>>>> REPLACE\n"
    )
    _patch_llm(monkeypatch, bad_block + good_block)

    result = apply_ai_fix("core/util.py", ORIGINAL, _Plan(), {"summary": "dead()"})

    assert "return {" not in result
    assert "def dead()" not in result
    assert "def used()" in result


def test_apply_ai_fix_reports_progress(monkeypatch):
    fixed = "import os\n\n\ndef used():\n    return 1\n"
    _patch_llm(monkeypatch, f"```python\n{fixed}```")

    events = []
    apply_ai_fix(
        "core/util.py", ORIGINAL, _Plan(), {},
        progress=lambda pct, phase, msg: events.append((pct, phase)),
    )

    percents = [p for p, _ in events]
    phases = [ph for _, ph in events]
    assert percents[0] == 0 and percents[-1] == 100
    assert percents == sorted(percents)        # monotonic
    assert "done" in phases


=======
>>>>>>> c88ee3e (feat(ai-fixes): SEARCH/REPLACE edit blocks for any-size files)
def test_apply_ai_fix_rejects_invalid_python(monkeypatch):
    _patch_llm(monkeypatch, "```python\ndef broken(:\n    pass\n```")

    with pytest.raises(AIFixError):
        apply_ai_fix("core/util.py", ORIGINAL, _Plan(), {})


def test_apply_ai_fix_rejects_no_change(monkeypatch):
    _patch_llm(monkeypatch, f"```\n{ORIGINAL}```")

    with pytest.raises(AIFixError):
        apply_ai_fix("core/util.py", ORIGINAL, _Plan(), {})


def test_apply_ai_fix_rejects_oversized_rewrite(monkeypatch):
    huge = "".join(f"x{i} = {i}\n" for i in range(200))
    _patch_llm(monkeypatch, f"```\n{huge}```")

    with pytest.raises(AIFixError):
        apply_ai_fix("core/util.py", ORIGINAL, _Plan(), {})


def test_ai_fixable_paths_filters_by_category_and_extension():
    assert ai_fixes.ai_fixable_paths(_Plan(category="docs")) == []
    plan = _Plan(category="dead_code", changed_paths=["a.py", "b.md", "../evil.py", "c.ts"])
    assert ai_fixes.ai_fixable_paths(plan) == ["a.py", "c.ts"]


def test_has_ai_fix_true_for_supported_category():
    assert ai_fixes.has_ai_fix(_Plan(category="dead_code")) is True
    assert ai_fixes.has_ai_fix(_Plan(category="docs")) is False
