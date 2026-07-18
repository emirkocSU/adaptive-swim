"""Explicit 1.0 -> 1.1 migration (§4.1)."""

from __future__ import annotations

import pytest

from contracts.enums import StartMode, WorkoutGoal
from contracts.workout import WorkoutTemplateV1_0
from swimcore.workout import migrate_workout_1_0_to_1_1


def _wk10() -> WorkoutTemplateV1_0:
    return WorkoutTemplateV1_0.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "legacy 200",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 200,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 200, "mode": "even_pace", "targetPaceSecPer100M": 80.0}
                    ],
                }
            ],
        }
    )


def test_migration_requires_explicit_start_mode() -> None:
    with pytest.raises(TypeError):
        # Missing keyword -> the caller cannot migrate without deciding the start mode.
        migrate_workout_1_0_to_1_1(_wk10())  # type: ignore[call-arg]


def test_migration_preserves_distance_and_pace() -> None:
    wk11 = migrate_workout_1_0_to_1_1(
        _wk10(),
        explicit_default_start_mode=StartMode.DIVE_START,
        workout_goal=WorkoutGoal.RACE_PACE,
    )
    assert wk11.schemaVersion == "1.1"
    assert wk11.poolLengthM == 25
    assert wk11.stroke.value == "freestyle"
    assert wk11.blocks[0].distanceM == 200
    assert wk11.blocks[0].segments[0].targetPaceSecPer100M == 80.0
    assert wk11.startPolicy.defaultMode is StartMode.DIVE_START


def test_migration_does_not_guess_start_mode() -> None:
    # Whatever the caller passes is what is used; no heuristic on the legacy workout.
    wk11 = migrate_workout_1_0_to_1_1(
        _wk10(), explicit_default_start_mode=StartMode.IN_WATER_PUSH_START
    )
    assert wk11.startPolicy.defaultMode is StartMode.IN_WATER_PUSH_START
