"""Commit 4 — timeline compilation, boundary continuity, range/clamp, wall helpers."""

from __future__ import annotations

import math

import pytest

from contracts.workout import WorkoutTemplateVersion
from swimcore.pacing import (
    DistanceOutsideTimelineError,
    InvalidDistanceError,
    InvalidDurationError,
    TimeOutsideTimelineError,
    compile_pace_timeline,
    ghost_distance_at_active_time,
    is_wall_boundary,
    next_wall_boundary,
    previous_wall_boundary,
    target_active_time_at_distance,
)


def _workout(blocks: list[dict], pool: int = 25) -> WorkoutTemplateVersion:
    return WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "tl",
            "poolLengthM": pool,
            "stroke": "freestyle",
            "blocks": blocks,
        }
    )


def _even_block(dist: int, reps: int, pace: float) -> dict:
    return {
        "type": "repeat",
        "repetitions": reps,
        "distanceM": dist,
        "rest": {"type": "fixed", "restSec": 20},
        "segments": [{"fromM": 0, "toM": dist, "mode": "even_pace", "targetPaceSecPer100M": pace}],
    }


def test_repeat_block_expansion() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 10, 80.0)]))
    assert len(tl.intervals) == 10
    assert tl.totalDistanceM == 1000.0


def test_multiple_blocks_timeline() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 4, 80.0), _even_block(50, 8, 40.0)]))
    assert tl.totalDistanceM == 400 + 400
    assert len(tl.intervals) == 12


def test_rest_excluded_from_active_timeline() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 10, 80.0)]))
    # 10 * 80 s active = 800 s; rest (10*20) is NOT included
    assert tl.totalActiveDurationSec == pytest.approx(800.0)


def test_segment_repeat_block_boundary_continuity() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 2, 80.0), _even_block(100, 1, 60.0)]))
    # cumulative time is continuous and strictly increasing across all boundaries
    prev_t = 0.0
    for d in (100, 200, 300):
        t = target_active_time_at_distance(tl, d).elapsedActiveSec
        assert t > prev_t
        prev_t = t
    assert target_active_time_at_distance(tl, 300).elapsedActiveSec == pytest.approx(
        tl.totalActiveDurationSec
    )


def test_time_at_total_distance() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 10, 80.0)]))
    assert target_active_time_at_distance(tl, 1000).elapsedActiveSec == pytest.approx(800.0)
    assert target_active_time_at_distance(tl, 0).elapsedActiveSec == 0.0


def test_distance_at_total_active_time() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 10, 80.0)]))
    assert ghost_distance_at_active_time(tl, 800).distanceM == pytest.approx(1000.0)
    assert ghost_distance_at_active_time(tl, 0).distanceM == 0.0


def test_out_of_range_distance_rejected() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 1, 80.0)]))
    with pytest.raises(DistanceOutsideTimelineError):
        target_active_time_at_distance(tl, 500)
    with pytest.raises(InvalidDistanceError):
        target_active_time_at_distance(tl, -1)


def test_out_of_range_active_time_rejected() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 1, 80.0)]))
    with pytest.raises(TimeOutsideTimelineError):
        ghost_distance_at_active_time(tl, 5000)
    with pytest.raises(InvalidDurationError):
        ghost_distance_at_active_time(tl, -1)


def test_clamped_active_time() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 1, 80.0)]))
    res = ghost_distance_at_active_time(tl, 5000, clamp=True)
    assert res.clamped and res.distanceM == pytest.approx(tl.totalDistanceM)


def test_25m_wall_boundaries() -> None:
    assert is_wall_boundary(100, 25)
    assert not is_wall_boundary(110, 25)
    assert previous_wall_boundary(110, 25) == 100.0
    assert next_wall_boundary(110, 25, 1000) == 125.0


def test_50m_wall_boundaries() -> None:
    assert is_wall_boundary(400, 50)
    assert previous_wall_boundary(430, 50) == 400.0
    assert next_wall_boundary(430, 50, 800) == 450.0


def test_next_wall_at_final_distance_is_clamped() -> None:
    assert next_wall_boundary(1000, 25, 1000) == 1000.0


def test_input_workout_is_not_mutated() -> None:
    w = _workout([_even_block(100, 3, 80.0)])
    before = w.model_dump()
    compile_pace_timeline(w)
    assert w.model_dump() == before


def test_deterministic_repeated_calls() -> None:
    w = _workout([_even_block(100, 5, 80.0)])
    a = compile_pace_timeline(w)
    b = compile_pace_timeline(w)
    assert a == b
    assert target_active_time_at_distance(a, 250) == target_active_time_at_distance(b, 250)


# --------------------------------------------------------------------------- A3 compiler guards
def _bad(segments: list[dict], dist: int, pool: int = 25, adaptation: dict | None = None) -> dict:
    block: dict = {
        "type": "repeat",
        "repetitions": 1,
        "distanceM": dist,
        "rest": {"type": "none"},
        "segments": segments,
    }
    if adaptation is not None:
        block["adaptation"] = adaptation
    return {
        "schemaVersion": "1.0",
        "name": "bad",
        "poolLengthM": pool,
        "stroke": "freestyle",
        "blocks": [block],
    }


def _seg(a: float, b: float, mode: str = "even_pace", **extra: object) -> dict:
    seg: dict = {"fromM": a, "toM": b, "mode": mode, "targetPaceSecPer100M": 83.0}
    seg.update(extra)
    return seg


def test_compile_rejects_segment_gap() -> None:
    from swimcore.pacing import InvalidPaceCurveError

    w = WorkoutTemplateVersion.model_validate(_bad([_seg(0, 50), _seg(100, 200)], 200))
    with pytest.raises(InvalidPaceCurveError):
        compile_pace_timeline(w)


def test_compile_rejects_invalid_controlled_start_direction() -> None:
    from swimcore.pacing import InvalidPaceCurveError

    seg = _seg(0, 100, "controlled_start", targetPaceSecPer100M=80.0, startPaceSecPer100M=76.0)
    w = WorkoutTemplateVersion.model_validate(_bad([seg], 100))
    with pytest.raises(InvalidPaceCurveError):
        compile_pace_timeline(w)


def test_compile_rejects_invalid_progressive_direction() -> None:
    from swimcore.pacing import InvalidPaceCurveError

    seg = _seg(0, 100, "progressive", targetPaceSecPer100M=80.0, endPaceSecPer100M=88.0)
    w = WorkoutTemplateVersion.model_validate(_bad([seg], 100))
    with pytest.raises(InvalidPaceCurveError):
        compile_pace_timeline(w)


def test_compile_rejects_invalid_negative_split() -> None:
    from swimcore.pacing import InvalidPaceCurveError

    segs = [
        _seg(0, 100, "negative_split_part", targetPaceSecPer100M=78.0),
        _seg(100, 200, "negative_split_part", targetPaceSecPer100M=82.0),
    ]
    w = WorkoutTemplateVersion.model_validate(_bad(segs, 200))
    with pytest.raises(InvalidPaceCurveError):
        compile_pace_timeline(w)


# --------------------------------------------------------------------------- A4 numeric guards
def test_wall_helpers_reject_nan_and_infinity() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(InvalidDistanceError):
            is_wall_boundary(bad, 25)
        with pytest.raises(InvalidDistanceError):
            previous_wall_boundary(bad, 25)
        with pytest.raises(InvalidDistanceError):
            next_wall_boundary(bad, 25, 1000)


def test_next_wall_rejects_negative_total_distance() -> None:
    with pytest.raises(InvalidDistanceError):
        next_wall_boundary(10, 25, -100)


def test_next_wall_rejects_distance_above_total() -> None:
    with pytest.raises(InvalidDistanceError):
        next_wall_boundary(500, 25, 400)


def test_next_wall_never_returns_previous_distance() -> None:
    assert next_wall_boundary(110, 25, 1000) >= 110
    assert next_wall_boundary(1000, 25, 1000) >= 1000


def test_timeline_queries_reject_nan_and_infinity() -> None:
    tl = compile_pace_timeline(_workout([_even_block(100, 1, 80.0)]))
    for bad in (math.nan, math.inf):
        with pytest.raises(InvalidDistanceError):
            target_active_time_at_distance(tl, bad)
        with pytest.raises(InvalidDurationError):
            ghost_distance_at_active_time(tl, bad)


def test_next_wall_rejects_non_wall_total_distance() -> None:
    # 90 m is not a wall in a 25 m pool → no valid wall between 80 and 90.
    with pytest.raises(InvalidDistanceError):
        next_wall_boundary(80.0, 25, 90.0)


def test_next_wall_always_returns_a_wall_multiple() -> None:
    # when the total is a wall, the clamp still yields a wall
    assert is_wall_boundary(next_wall_boundary(990.0, 25, 1000.0), 25)
    assert next_wall_boundary(990.0, 25, 1000.0) == 1000.0
