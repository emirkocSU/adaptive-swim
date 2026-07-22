from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from analytics.serialization import encode_session_report
from tests.unit._analytics_helpers import report


@given(st.lists(st.integers(min_value=15_000, max_value=30_000), min_size=4, max_size=4))
def test_same_inputs_produce_same_report(durations: list[int]) -> None:
    cumulative: list[int] = []
    total = 0
    for duration in durations:
        total += duration
        cumulative.append(total)
    timestamps = tuple(cumulative)
    first = report(timestamps)
    second = report(timestamps)
    assert first == second
    assert encode_session_report(first) == encode_session_report(second)
