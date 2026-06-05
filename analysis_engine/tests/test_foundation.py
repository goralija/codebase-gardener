from gardener_analysis import foundation_status


def test_foundation_status_marks_repowise_as_reserved():
    assert foundation_status() == {
        "package": "gardener_analysis",
        "status": "ready",
        "repowise": "reserved_for_lane_b",
    }

