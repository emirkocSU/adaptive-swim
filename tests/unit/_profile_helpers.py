"""Shared builders for the approved-profile mainline tests."""

from __future__ import annotations

import json
from pathlib import Path

from contracts.pace_profiles import ApprovedPaceProfile
from contracts.workout import WorkoutTemplateV1_1
from swimcore.session import FixedClock, SequenceIdGenerator, SessionAggregate

_EXAMPLES = Path(__file__).resolve().parents[2] / "src" / "contracts" / "examples"
_V1_1 = _EXAMPLES / "valid_v1_1"


def load_profile(name: str) -> ApprovedPaceProfile:
    data = json.loads((_V1_1 / name).read_text(encoding="utf-8"))
    return ApprovedPaceProfile(**data)


def workout_1_1(
    *,
    pool: int = 25,
    stroke: str = "freestyle",
    distance: int = 200,
    default_start: str = "DIVE_START",
    goal: str = "RACE_PACE",
    allow_block: bool = True,
    allow_repeat: bool = True,
    repeat_overrides: list[dict] | None = None,
    block_start_mode: str | None = None,
) -> WorkoutTemplateV1_1:
    block: dict = {
        "type": "repeat",
        "label": "main",
        "repetitions": 1,
        "distanceM": distance,
        "rest": {"type": "none"},
        "segments": [
            {"fromM": 0, "toM": distance, "mode": "even_pace", "targetPaceSecPer100M": 70.0}
        ],
    }
    if block_start_mode is not None:
        block["startMode"] = block_start_mode
    return WorkoutTemplateV1_1.model_validate(
        {
            "schemaVersion": "1.1",
            "name": "wk11",
            "poolLengthM": pool,
            "stroke": stroke,
            "startPolicy": {
                "defaultMode": default_start,
                "allowBlockOverride": allow_block,
                "allowRepeatOverride": allow_repeat,
            },
            "workoutGoal": goal,
            "blocks": [block],
            "repeatOverrides": repeat_overrides or [],
        }
    )


def profile_aggregate(
    profile: ApprovedPaceProfile,
    wk: WorkoutTemplateV1_1,
    *,
    allow_default_model: bool = False,
) -> tuple[SessionAggregate, FixedClock]:
    clk = FixedClock(0)
    agg = SessionAggregate(
        {},
        clk,
        SequenceIdGenerator(),
        profiles={"p1": profile},
        workouts_v1_1={"w1": wk},
    )
    return agg, clk


def create_profile_session(
    agg: SessionAggregate,
    *,
    allow_default_model: bool = False,
    first_repeat_index: int = 0,
) -> None:
    from contracts.commands import CreateSession

    agg.handle(
        CreateSession(
            clientCommandId="create",
            workoutRef="w1",
            paceProfileRef="p1",
            firstRepeatIndex=first_repeat_index,
            allowDefaultModelProfile=allow_default_model,
        )
    )
