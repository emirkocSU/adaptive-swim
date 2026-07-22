from __future__ import annotations

from tests.unit._analytics_helpers import report


def test_official_distance_uses_wall_count_and_pool_geometry() -> None:
    distance = report().distanceSummary
    assert distance.plannedDistanceM == 100
    assert distance.officialCompletedDistanceM == 100
    assert distance.completedLengthCount == 4
    assert distance.completionRatio == 1
    assert distance.partial is False
