"""Workout 1.1 schema + start-policy structural tests (§4, §6, §22.2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.workout import (
    RepeatExecutionOverride,
    StartPolicy,
    WorkoutTemplateV1_0,
    WorkoutTemplateV1_1,
)


def _wk11(**over: object) -> dict:
    base: dict = {
        "schemaVersion": "1.1",
        "name": "wk",
        "poolLengthM": 25,
        "stroke": "freestyle",
        "startPolicy": {"defaultMode": "DIVE_START"},
        "workoutGoal": "RACE_PACE",
        "blocks": [
            {
                "type": "repeat",
                "repetitions": 2,
                "distanceM": 100,
                "rest": {"type": "none"},
                "segments": [
                    {"fromM": 0, "toM": 100, "mode": "even_pace", "targetPaceSecPer100M": 70.0}
                ],
            }
        ],
    }
    base.update(over)
    return base


def test_workout_1_0_schema_remains_available() -> None:
    wk = WorkoutTemplateV1_0.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "legacy",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 100,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 100, "mode": "even_pace", "targetPaceSecPer100M": 80.0}
                    ],
                }
            ],
        }
    )
    assert wk.schemaVersion == "1.0"


def test_workout_1_1_requires_start_policy() -> None:
    data = _wk11()
    del data["startPolicy"]
    with pytest.raises(ValidationError):
        WorkoutTemplateV1_1.model_validate(data)


def test_workout_1_1_requires_workout_goal() -> None:
    data = _wk11()
    del data["workoutGoal"]
    with pytest.raises(ValidationError):
        WorkoutTemplateV1_1.model_validate(data)


def test_duplicate_repeat_override_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkoutTemplateV1_1.model_validate(
            _wk11(
                repeatOverrides=[
                    {"repeatIndex": 0, "startMode": "DIVE_START"},
                    {"repeatIndex": 0, "startMode": "IN_WATER_PUSH_START"},
                ]
            )
        )


def test_repeat_override_rejected_when_policy_disallows() -> None:
    with pytest.raises(ValidationError):
        WorkoutTemplateV1_1.model_validate(
            _wk11(
                startPolicy={"defaultMode": "DIVE_START", "allowRepeatOverride": False},
                repeatOverrides=[{"repeatIndex": 0, "startMode": "IN_WATER_PUSH_START"}],
            )
        )


def test_block_override_rejected_when_policy_disallows() -> None:
    data = _wk11(startPolicy={"defaultMode": "DIVE_START", "allowBlockOverride": False})
    data["blocks"][0]["startMode"] = "IN_WATER_PUSH_START"
    with pytest.raises(ValidationError):
        WorkoutTemplateV1_1.model_validate(data)


def test_start_policy_defaults_allow_overrides() -> None:
    sp = StartPolicy(defaultMode="DIVE_START")
    assert sp.allowBlockOverride and sp.allowRepeatOverride


def test_repeat_execution_override_shape() -> None:
    ov = RepeatExecutionOverride(repeatIndex=1, startMode="IN_WATER_PUSH_START")
    assert ov.repeatIndex == 1
