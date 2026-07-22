from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tests.unit._analytics_helpers import report


@given(st.lists(st.integers(min_value=15_000, max_value=30_000), min_size=4, max_size=4))
def test_split_metric_ranges_and_counts(durations: list[int]) -> None:
    timestamps: list[int] = []
    total = 0
    for duration in durations:
        total += duration
        timestamps.append(total)
    result = report(tuple(timestamps))
    aggregate = result.splitAnalysis.aggregate
    assert aggregate.eligibleSplitCount <= result.distanceSummary.officialSplitCount
    if aggregate.targetPaceAdherenceRatio is not None:
        assert 0 <= aggregate.targetPaceAdherenceRatio <= 1
    if result.distanceSummary.completionRatio is not None:
        assert 0 <= result.distanceSummary.completionRatio <= 1
    assert all(split.actualDurationSec >= 0 for split in result.splitAnalysis.splits)
