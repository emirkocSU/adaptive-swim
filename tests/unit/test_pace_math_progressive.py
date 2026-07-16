"""Commit 4 — progressive pace curve: linear pace, exact integral, quadratic inverse."""

from __future__ import annotations

import pytest

from contracts.workout import WorkoutTemplateVersion
from swimcore.pacing import (
    compile_pace_timeline,
    ghost_distance_at_active_time,
    target_active_time_at_distance,
)
from swimcore.pacing.curves import pace_at_local_distance


def _progressive(target: float, end: float, dist: int = 100) -> WorkoutTemplateVersion:
    return WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "prog",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": dist,
                    "rest": {"type": "none"},
                    "segments": [
                        {
                            "fromM": 0,
                            "toM": dist,
                            "mode": "progressive",
                            "targetPaceSecPer100M": target,
                            "endPaceSecPer100M": end,
                        }
                    ],
                }
            ],
        }
    )


def test_progressive_exact_total_duration() -> None:
    tl = compile_pace_timeline(_progressive(84.0, 76.0))
    # L*(p0+p1)/200 = 100*(84+76)/200 = 80
    assert tl.totalActiveDurationSec == pytest.approx(80.0)


def test_progressive_midpoint_pace() -> None:
    # linear in distance: at x = L/2 pace is the mean of endpoints
    assert pace_at_local_distance(50, 100, 84.0, 76.0) == pytest.approx(80.0)


def test_progressive_pace_is_monotonic() -> None:
    prev = None
    for x in range(0, 101, 10):
        p = pace_at_local_distance(x, 100, 84.0, 76.0)
        if prev is not None:
            assert p <= prev + 1e-9  # getting faster (smaller) toward the end
        prev = p


def test_progressive_inverse_quadratic_solution() -> None:
    tl = compile_pace_timeline(_progressive(84.0, 76.0))
    for d in (12.3, 40.0, 63.7, 99.9):
        t = target_active_time_at_distance(tl, d).elapsedActiveSec
        back = ghost_distance_at_active_time(tl, t).distanceM
        assert abs(back - d) < 1e-6


def test_progressive_not_linear_time_ratio() -> None:
    # Because pace varies, time-at-half-distance is NOT half the total duration.
    tl = compile_pace_timeline(_progressive(84.0, 76.0))
    half = target_active_time_at_distance(tl, 50.0).elapsedActiveSec
    assert half != pytest.approx(tl.totalActiveDurationSec / 2)
