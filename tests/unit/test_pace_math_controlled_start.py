"""Commit 4 — controlled-start pace curve (start slower/equal → target)."""

from __future__ import annotations

import pytest

from contracts.workout import WorkoutTemplateVersion
from swimcore.pacing import InvalidPaceCurveError, compile_pace_timeline
from swimcore.pacing.curves import resolve_curve_endpoints


def _workout(segment: dict) -> WorkoutTemplateVersion:
    return WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "cs",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 100,
                    "rest": {"type": "none"},
                    "segments": [segment],
                }
            ],
        }
    )


def test_controlled_start_valid_curve() -> None:
    p0, p1 = resolve_curve_endpoints("controlled_start", 80.0, 88.0, None)
    assert (p0, p1) == (88.0, 80.0)  # start slower (larger), end at target
    tl = compile_pace_timeline(
        _workout(
            {
                "fromM": 0,
                "toM": 100,
                "mode": "controlled_start",
                "targetPaceSecPer100M": 80.0,
                "startPaceSecPer100M": 88.0,
            }
        )
    )
    interval = tl.intervals[0]
    # start pace numerically larger (slower) than end pace (faster)
    assert interval.startPaceSecPer100M > interval.endPaceSecPer100M
    # duration = L*(p0+p1)/200 = 100*(88+80)/200
    assert interval.activeDurationSec == pytest.approx(100 * (88 + 80) / 200)


def test_controlled_start_missing_start_pace_raises() -> None:
    with pytest.raises(InvalidPaceCurveError):
        resolve_curve_endpoints("controlled_start", 80.0, None, None)


def test_controlled_start_endpoints_reflect_direction() -> None:
    # A "becoming slower incorrectly" start (start faster than target) is a *validator*
    # concern; the math layer faithfully reflects the given endpoints without silent fixes.
    p0, p1 = resolve_curve_endpoints("controlled_start", 80.0, 76.0, None)
    assert p0 == 76.0 and p1 == 80.0  # no magic correction applied
