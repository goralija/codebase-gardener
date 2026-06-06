from gardener_analysis import foundation_status


def test_foundation_status_marks_indexed_fixture_wrapper_ready():
    assert foundation_status() == {
        "package": "gardener_analysis",
        "status": "ready",
        "repowise": "indexed_fixture_wrapper_ready",
    }
