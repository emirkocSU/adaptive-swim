"""Commit 4 — negative-split structures (partition + negative_split_part ordering)."""

from __future__ import annotations

import pytest

from contracts.workout import WorkoutTemplateVersion
from swimcore.pacing import compile_pace_timeline, target_active_time_at_distance
from swimcore.workout import RuleCode, WorkoutValidationContext, validate_workout


def _two_part(first: float, second: float, mode: str = "even_pace") -> WorkoutTemplateVersion:
    return WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "ns",
            "poolLengthM": 50,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 800,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 400, "mode": mode, "targetPaceSecPer100M": first},
                        {"fromM": 400, "toM": 800, "mode": mode, "targetPaceSecPer100M": second},
                    ],
                }
            ],
        }
    )


def test_partitioned_negative_split_compiles() -> None:
    # second half faster (smaller) than first half
    tl = compile_pace_timeline(_two_part(82.0, 78.0))
    assert tl.totalDistanceM == 800.0
    # first 400 m @ 82, next 400 m @ 78
    assert tl.intervals[0].activeDurationSec == pytest.approx(400 * 82 / 100)
    assert tl.intervals[1].activeDurationSec == pytest.approx(400 * 78 / 100)
    # time is continuous across the split boundary
    at_400 = target_active_time_at_distance(tl, 400).elapsedActiveSec
    assert at_400 == pytest.approx(tl.intervals[0].activeDurationSec)


def test_negative_split_part_valid_ordering() -> None:
    w = _two_part(82.0, 78.0, mode="negative_split_part")
    result = validate_workout(w, WorkoutValidationContext())
    assert not any(i.rule == RuleCode.NEGATIVE_SPLIT_ORDER_INVALID for i in result.issues)


def test_negative_split_part_invalid_ordering() -> None:
    # second part slower (numerically larger) than the first → invalid
    w = _two_part(78.0, 82.0, mode="negative_split_part")
    result = validate_workout(w, WorkoutValidationContext())
    assert any(i.rule == RuleCode.NEGATIVE_SPLIT_ORDER_INVALID for i in result.errors)
    assert not result.isValid
