import pytest

from apps.maintenance_prs.roi import estimate_roi, _hours_saved_range, _high_entropy_delta_count


def opportunity(
    category="docs",
    confidence=0.94,
    affected_paths=None,
    expected_entropy_delta=-2.1,
):
    return {
        "maintenance_opportunity_id": "opp_test",
        "category": category,
        "confidence": confidence,
        "affected_paths": affected_paths if affected_paths is not None else ["README.md"],
        "expected_entropy_delta": expected_entropy_delta,
        "title": "Test opportunity",
        "summary": "Test summary",
    }


def test_roi_normal_case():
    group = [opportunity("docs", 0.94, ["README.md", "docs/spec.md"], -2.1)]
    result = estimate_roi(group)
    assert "engineering hours saved" in result
    assert "high-entropy-delta" in result
    assert "Assumptions" in result
    assert "indicative only" in result


def test_roi_high_impact_category():
    group = [opportunity("dead_code", 0.99, ["src/old.py", "src/unused.py"], -3.0)]
    low, high = _hours_saved_range(group)
    assert high > 2.0  # 3.0 hrs/file * 2 files * 0.99 = ~5.9
    assert low == pytest.approx(high * 0.5)


def test_roi_docs_lower_than_dead_code():
    docs_group = [opportunity("docs", 1.0, ["README.md"])]
    dead_group = [opportunity("dead_code", 1.0, ["src/old.py"])]
    _, docs_high = _hours_saved_range(docs_group)
    _, dead_high = _hours_saved_range(dead_group)
    assert dead_high > docs_high


def test_roi_missing_paths():
    group = [opportunity("docs", 0.94, [])]
    low, high = _hours_saved_range(group)
    assert low == 0.0
    assert high == 0.0
    result = estimate_roi(group)
    assert "engineering hours saved" not in result
    assert "Assumptions" in result


def test_roi_no_high_delta_when_above_threshold():
    group = [opportunity("docs", 0.94, ["README.md"], expected_entropy_delta=-0.5)]
    assert _high_entropy_delta_count(group) == 0
    result = estimate_roi(group)
    assert "high-entropy-delta" not in result


def test_roi_high_delta_counted_when_below_threshold():
    group = [opportunity("docs", 0.94, ["README.md"], expected_entropy_delta=-1.5)]
    assert _high_entropy_delta_count(group) == 1


def test_roi_missing_entropy_delta():
    opp = {
        "maintenance_opportunity_id": "opp_test",
        "category": "docs",
        "confidence": 0.94,
        "affected_paths": ["README.md"],
        "title": "Test",
        "summary": "Test",
    }
    assert _high_entropy_delta_count([opp]) == 0


def test_roi_blocked_plan_returns_no_estimate():
    group = [opportunity()]
    result = estimate_roi(group, blocked=True)
    assert "blocked" in result
    assert "hours saved" not in result


def test_roi_low_confidence():
    group = [opportunity("docs", 0.0, ["README.md"])]
    low, high = _hours_saved_range(group)
    assert low == 0.0
    assert high == 0.0


def test_roi_multi_opportunity_group():
    group = [
        opportunity("docs", 0.94, ["README.md"], -2.0),
        opportunity("docs", 0.90, ["docs/api.md"], -1.5),
    ]
    _, high = _hours_saved_range(group)
    # 0.5 * 1 * 0.94 + 0.5 * 1 * 0.90 = 0.47 + 0.45 = 0.92
    assert high == pytest.approx(0.92, abs=0.01)
    assert _high_entropy_delta_count(group) == 2


def test_roi_output_is_string():
    group = [opportunity()]
    result = estimate_roi(group)
    assert isinstance(result, str)
    assert len(result) > 0


def test_roi_assumptions_include_category_rate():
    group = [opportunity("dead_code", 0.95, ["old.py"], -3.0)]
    result = estimate_roi(group)
    assert "dead_code" in result
    assert "3.0 hrs/file" in result


def test_roi_unknown_category_uses_default():
    group = [opportunity("unknown_type", 1.0, ["file.py"], 0.0)]
    _, high = _hours_saved_range(group)
    assert high == pytest.approx(1.0)  # DEFAULT_HOURS_PER_FILE * 1 file * 1.0 confidence
