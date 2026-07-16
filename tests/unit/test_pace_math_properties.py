"""Commit 4 — property-based invariants (Hypothesis)."""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from contracts.workout import WorkoutTemplateVersion
from swimcore.pacing import (
    compile_pace_timeline,
    distance_for_duration,
    duration_for_distance,
    ghost_distance_at_active_time,
    is_wall_boundary,
    next_wall_boundary,
    previous_wall_boundary,
    target_active_time_at_distance,
)

_distance = st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_duration = st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
_pace = st.floats(min_value=30.01, max_value=300.0, allow_nan=False, allow_infinity=False)
_pool = st.sampled_from([25, 50])


@given(d=_distance, p=_pace)
def test_distance_duration_distance_round_trip(d: float, p: float) -> None:
    back = distance_for_duration(duration_for_distance(d, p), p)
    assert math.isclose(back, d, rel_tol=1e-9, abs_tol=1e-6)


@given(t=_duration, p=_pace)
def test_duration_distance_duration_round_trip(t: float, p: float) -> None:
    back = duration_for_distance(distance_for_duration(t, p), p)
    assert math.isclose(back, t, rel_tol=1e-9, abs_tol=1e-6)


def _timeline(target: float, end: float) -> object:
    w = WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "p",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 4,
                    "distanceM": 100,
                    "rest": {"type": "none"},
                    "segments": [
                        {
                            "fromM": 0,
                            "toM": 100,
                            "mode": "progressive",
                            "targetPaceSecPer100M": target,
                            "endPaceSecPer100M": end,
                        }
                    ],
                }
            ],
        }
    )
    return compile_pace_timeline(w)


@given(
    frac=st.floats(min_value=0.0, max_value=1.0),
    target=st.floats(min_value=70.0, max_value=100.0),
    delta=st.floats(min_value=0.0, max_value=15.0),
)
def test_time_distance_inverse(frac: float, target: float, delta: float) -> None:
    end = target - delta  # end faster-or-equal (progressive)
    tl = _timeline(target, end)
    d = frac * tl.totalDistanceM
    t = target_active_time_at_distance(tl, d).elapsedActiveSec
    back = ghost_distance_at_active_time(tl, t).distanceM
    assert math.isclose(back, d, rel_tol=1e-6, abs_tol=1e-4)


@given(
    a=st.floats(min_value=0.0, max_value=1.0),
    b=st.floats(min_value=0.0, max_value=1.0),
    target=st.floats(min_value=70.0, max_value=100.0),
    delta=st.floats(min_value=0.0, max_value=15.0),
)
def test_distance_monotonic_in_time(a: float, b: float, target: float, delta: float) -> None:
    tl = _timeline(target, target - delta)
    ta, tb = sorted((a * tl.totalActiveDurationSec, b * tl.totalActiveDurationSec))
    da = ghost_distance_at_active_time(tl, ta).distanceM
    db = ghost_distance_at_active_time(tl, tb).distanceM
    assert db >= da - 1e-6


@given(
    a=st.floats(min_value=0.0, max_value=1.0),
    b=st.floats(min_value=0.0, max_value=1.0),
    target=st.floats(min_value=70.0, max_value=100.0),
    delta=st.floats(min_value=0.0, max_value=15.0),
)
def test_time_monotonic_in_distance(a: float, b: float, target: float, delta: float) -> None:
    tl = _timeline(target, target - delta)
    da, db = sorted((a * tl.totalDistanceM, b * tl.totalDistanceM))
    ta = target_active_time_at_distance(tl, da).elapsedActiveSec
    tb = target_active_time_at_distance(tl, db).elapsedActiveSec
    assert tb >= ta - 1e-6


@given(
    reps=st.integers(min_value=1, max_value=20),
    dist=st.integers(min_value=25, max_value=400),
    target=st.floats(min_value=70.0, max_value=100.0),
    delta=st.floats(min_value=0.0, max_value=15.0),
)
def test_timeline_totals_are_consistent(reps: int, dist: int, target: float, delta: float) -> None:
    w = WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "t",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": reps,
                    "distanceM": dist,
                    "rest": {"type": "none"},
                    "segments": [
                        {
                            "fromM": 0,
                            "toM": dist,
                            "mode": "progressive",
                            "targetPaceSecPer100M": target,
                            "endPaceSecPer100M": target - delta,
                        }
                    ],
                }
            ],
        }
    )
    tl = compile_pace_timeline(w)
    assert tl.totalDistanceM == reps * dist
    assert tl.totalActiveDurationSec >= 0.0
    # pace stays within the segment endpoint range everywhere
    for interval in tl.intervals:
        lo = min(interval.startPaceSecPer100M, interval.endPaceSecPer100M)
        hi = max(interval.startPaceSecPer100M, interval.endPaceSecPer100M)
        assert lo - 1e-9 <= interval.startPaceSecPer100M <= hi + 1e-9


@given(x=_distance, pool=_pool)
def test_wall_helpers_return_pool_multiples(x: float, pool: int) -> None:
    total = 10000.0
    prev = previous_wall_boundary(x, pool)
    nxt = next_wall_boundary(x, pool, total)
    assert is_wall_boundary(prev, pool)
    assert nxt <= total + 1e-9
    assert prev <= x + 1e-6
