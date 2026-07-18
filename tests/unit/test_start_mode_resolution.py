"""Start-mode resolution precedence (§6, §22.2)."""

from __future__ import annotations

import pytest

from contracts.enums import StartMode
from contracts.workout import WorkoutTemplateV1_1
from swimcore.workout import resolve_default_start_mode, resolve_repeat_start_mode
from swimcore.workout.start_mode import StartModeResolutionError
from tests.unit._profile_helpers import workout_1_1


def test_workout_default_start_mode_resolves() -> None:
    wk = workout_1_1(default_start="DIVE_START")
    assert resolve_default_start_mode(wk) is StartMode.DIVE_START
    assert resolve_repeat_start_mode(wk, 0, 0) is StartMode.DIVE_START


def test_block_start_mode_overrides_default() -> None:
    wk = workout_1_1(default_start="DIVE_START", block_start_mode="IN_WATER_PUSH_START")
    assert resolve_repeat_start_mode(wk, 0, 0) is StartMode.IN_WATER_PUSH_START


def test_repeat_override_resolves() -> None:
    wk = workout_1_1(
        default_start="DIVE_START",
        repeat_overrides=[{"repeatIndex": 0, "startMode": "IN_WATER_STATIC_START"}],
    )
    assert resolve_repeat_start_mode(wk, 0, 0) is StartMode.IN_WATER_STATIC_START


def test_repeat_override_takes_priority_over_block() -> None:
    wk = workout_1_1(
        default_start="DIVE_START",
        block_start_mode="IN_WATER_PUSH_START",
        repeat_overrides=[{"repeatIndex": 0, "startMode": "IN_WATER_STATIC_START"}],
    )
    assert resolve_repeat_start_mode(wk, 0, 0) is StartMode.IN_WATER_STATIC_START


def test_repeat_index_out_of_range_rejected() -> None:
    wk = workout_1_1()
    with pytest.raises(StartModeResolutionError):
        resolve_repeat_start_mode(wk, 0, 5)


def test_block_scoped_repeat_override_distinguishes_blocks() -> None:
    # Two blocks each have a repeat 0; an override on block 1 repeat 0 must not affect block 0.
    wk = WorkoutTemplateV1_1.model_validate(
        {
            "schemaVersion": "1.1",
            "name": "two-block",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "startPolicy": {"defaultMode": "DIVE_START"},
            "workoutGoal": "RACE_PACE",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 50,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 50, "mode": "even_pace", "targetPaceSecPer100M": 80.0}
                    ],
                },
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 50,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 50, "mode": "even_pace", "targetPaceSecPer100M": 80.0}
                    ],
                },
            ],
            "repeatOverrides": [
                {"blockIndex": 1, "repeatIndex": 0, "startMode": "IN_WATER_PUSH_START"}
            ],
        }
    )
    assert resolve_repeat_start_mode(wk, 0, 0) is StartMode.DIVE_START
    assert resolve_repeat_start_mode(wk, 1, 0) is StartMode.IN_WATER_PUSH_START
