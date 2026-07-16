"""Commit 4 — timeline compilation, boundary continuity, range/clamp, wall helpers."""

from __future__ import annotations

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
