"""Current interval/profile context resolves from current distance, not blocks[0] (§2.14)."""

from __future__ import annotations

from contracts.commands import ApplyCoachPaceTarget, ArmSession, CreateSession, StartSession
from contracts.enums import PaceRequestSource
from contracts.workout import WorkoutTemplateVersion
from swimcore.session import FixedClock, SequenceIdGenerator, SessionAggregate
from tests.unit._session_helpers import record_split


def _two_block_workout() -> WorkoutTemplateVersion:
    # Block 0: fast target 78, tight bounds around it. Block 1: slower target 88, own bounds.
    return WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "two-block",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 50,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 50, "mode": "even_pace", "targetPaceSecPer100M": 78.0}
                    ],
                    "adaptation": {
                        "mode": "bounded_auto",
                        "maxChangePercentPerLength": 5.0,
                        "fastestAllowedPaceSecPer100M": 76.0,
                        "slowestAllowedPaceSecPer100M": 80.0,
                    },
                },
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 50,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 50, "mode": "even_pace", "targetPaceSecPer100M": 88.0}
                    ],
                    "adaptation": {
                        "mode": "bounded_auto",
                        "maxChangePercentPerLength": 5.0,
                        "fastestAllowedPaceSecPer100M": 86.0,
                        "slowestAllowedPaceSecPer100M": 92.0,
                    },
                },
            ],
        }
    )


def _agg():
    clk = FixedClock(0)
    agg = SessionAggregate({"w1": _two_block_workout()}, clk, SequenceIdGenerator())
    agg.handle(CreateSession(clientCommandId="c", workoutRef="w1"))
    clk.set(100)
    agg.handle(ArmSession(clientCommandId="a", sessionId=agg.sessionId))
    clk.set(200)
    agg.handle(StartSession(clientCommandId="s", sessionId=agg.sessionId))
    return agg, clk


def test_current_interval_starts_in_first_block() -> None:
    agg, _ = _agg()
    iv = agg._current_interval()
    assert iv.blockIndex == 0
    assert iv.startPaceSecPer100M == 78.0


def test_second_block_uses_second_block_safety_bounds() -> None:
    agg, clk = _agg()
    # advance official distance into block 1 (past 50 m)
    agg.handle(record_split(agg, 0))  # 25 m
    agg.handle(record_split(agg, 1))  # 50 m -> now current distance at block boundary
    iv = agg._current_interval()
    assert iv.blockIndex == 1
    # a coach-manual change is clamped by block-1 fastest bound (86), not block-0 (76)
    clk.set(100000)
    events = agg.handle(
        ApplyCoachPaceTarget(
            clientCommandId="apt",
            sessionId=agg.sessionId,
            suggestedPaceSecPer100M=80.0,  # faster than block-1 fastest 86 -> clamp to 86
            source=PaceRequestSource.COACH_MANUAL,
            currentWallDistanceM=50.0,
            isWallBoundary=True,
        )
    )
    control = events[0].payload
    assert control.appliedPaceSecPer100M == 86.0
