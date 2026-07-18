"""Negative-split first part vs previous segment terminal pace (§5 fix)."""

from __future__ import annotations

from contracts.workout import WorkoutTemplateVersion
from swimcore.workout import RuleCode, validate_workout


def _wk(segments: list[dict]) -> WorkoutTemplateVersion:
    return WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "ns",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": segments[-1]["toM"],
                    "rest": {"type": "none"},
                    "segments": segments,
                }
            ],
        }
    )


def test_first_negative_split_slower_than_previous_terminal_is_rejected() -> None:
    # previous even segment terminal pace 80; first negative-split part 85 (slower) -> invalid
    wk = _wk(
        [
            {"fromM": 0, "toM": 50, "mode": "even_pace", "targetPaceSecPer100M": 80.0},
            {"fromM": 50, "toM": 100, "mode": "negative_split_part", "targetPaceSecPer100M": 85.0},
        ]
    )
    result = validate_workout(wk)
    assert not result.isValid
    assert any(i.rule == RuleCode.NEGATIVE_SPLIT_ORDER_INVALID.value for i in result.errors)


def test_first_negative_split_faster_than_previous_terminal_is_ok() -> None:
    wk = _wk(
        [
            {"fromM": 0, "toM": 50, "mode": "even_pace", "targetPaceSecPer100M": 80.0},
            {"fromM": 50, "toM": 100, "mode": "negative_split_part", "targetPaceSecPer100M": 78.0},
        ]
    )
    result = validate_workout(wk)
    assert result.isValid


def test_progressive_terminal_pace_used_for_comparison() -> None:
    # progressive end pace 79 is the terminal; a negative-split at 82 is slower -> invalid
    wk = _wk(
        [
            {
                "fromM": 0,
                "toM": 50,
                "mode": "progressive",
                "targetPaceSecPer100M": 84.0,
                "endPaceSecPer100M": 79.0,
            },
            {"fromM": 50, "toM": 100, "mode": "negative_split_part", "targetPaceSecPer100M": 82.0},
        ]
    )
    result = validate_workout(wk)
    assert not result.isValid
    assert any(i.rule == RuleCode.NEGATIVE_SPLIT_ORDER_INVALID.value for i in result.errors)
