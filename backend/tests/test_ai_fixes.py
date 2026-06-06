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
