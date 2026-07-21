"""Deterministic builders for the three golden replay journals (Commit 7).

Each builder drives the REAL SessionAggregate with a FixedClock and the deterministic
SequenceIdGenerator, so the same command sequence always yields byte-identical journals in
any directory (golden determinism, ADR-012/ADR-033).
"""

from __future__ import annotations

from pathlib import Path

from contracts.commands import (
    ApplyCoachPaceTarget,
    ArmSession,
    CoachPacingReset,
    CompleteSession,
    CreateSession,
    MarkStopPause,
    RecordSplit,
    ResolveStopPause,
    StartSession,
)
from contracts.enums import (
    AlignmentSource,
    SplitSource,
    StopDetectionSource,
    StopPauseTrigger,
)
from contracts.events import EventEnvelope
from contracts.workout import WorkoutTemplateVersion
from persistence.jsonl_event_log import JsonlSessionEventLog
from swimcore.session import FixedClock, SequenceIdGenerator, SessionAggregate

POOL_M = 25
DIST_M = 100
TARGET_PACE = 80.0

GOLDEN_NAMES = ("normal-session", "stop-pause-session", "coach-reset-session")


def golden_workout(adaptation: dict[str, object] | None = None) -> WorkoutTemplateVersion:
    block: dict[str, object] = {
        "type": "repeat",
        "repetitions": 1,
        "distanceM": DIST_M,
        "rest": {"type": "none"},
        "segments": [
            {"fromM": 0, "toM": DIST_M, "mode": "even_pace", "targetPaceSecPer100M": TARGET_PACE}
        ],
    }
    if adaptation is not None:
        block["adaptation"] = adaptation
    return WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "golden",
            "poolLengthM": POOL_M,
            "stroke": "freestyle",
            "blocks": [block],
        }
    )


def _bounded_adaptation() -> dict[str, object]:
    return {
        "mode": "bounded_auto",
        "maxChangePercentPerLength": 5.0,
        "fastestAllowedPaceSecPer100M": 76.0,
        "slowestAllowedPaceSecPer100M": 90.0,
    }


def _aggregate(
    wk: WorkoutTemplateVersion,
) -> tuple[SessionAggregate, FixedClock]:
    clk = FixedClock(0)
    agg = SessionAggregate({"w1": wk}, clk, SequenceIdGenerator("evt"))
    return agg, clk


def _split(agg: SessionAggregate, index: int, ts: int, suffix: str) -> RecordSplit:
    assert agg.sessionId is not None
    return RecordSplit(
        clientCommandId=f"split{index}-{suffix}",
        sessionId=agg.sessionId,
        splitId=f"split-{index}",
        lengthIndex=index,
        wallTimestampMs=ts,
        source=SplitSource.TOUCHPAD,
        distanceM=float((index + 1) * POOL_M),
    )


def build_normal_session_batches() -> list[list[EventEnvelope]]:
    """Create → Arm → Start → 4 splits → Complete (no stops, no pauses)."""
    agg, clk = _aggregate(golden_workout())
    batches: list[list[EventEnvelope]] = []
    batches.append(agg.handle(CreateSession(clientCommandId="create-001", workoutRef="w1")))
    sid = agg.sessionId
    assert sid is not None
    batches.append(agg.handle(ArmSession(clientCommandId="arm-001", sessionId=sid)))
    batches.append(agg.handle(StartSession(clientCommandId="start-001", sessionId=sid)))
    for i, ts in enumerate((20_000, 40_000, 60_000, 80_000)):
        batches.append(agg.handle(_split(agg, i, ts, "001")))
    clk.set(80_000)
    batches.append(agg.handle(CompleteSession(clientCommandId="complete-001", sessionId=sid)))
    return batches


def build_stop_pause_session_batches() -> list[list[EventEnvelope]]:
    """One retroactive MANUAL_INCIDENT StopPause resolved before the next wall split."""
    agg, clk = _aggregate(golden_workout())
    batches: list[list[EventEnvelope]] = []
    batches.append(agg.handle(CreateSession(clientCommandId="create-002", workoutRef="w1")))
    sid = agg.sessionId
    assert sid is not None
    batches.append(agg.handle(ArmSession(clientCommandId="arm-002", sessionId=sid)))
    batches.append(agg.handle(StartSession(clientCommandId="start-002", sessionId=sid)))
    batches.append(agg.handle(_split(agg, 0, 20_000, "002")))
    batches.append(
        agg.handle(
            MarkStopPause(
                clientCommandId="stop-002",
                sessionId=sid,
                trigger=StopPauseTrigger.MANUAL_INCIDENT,
                stopStartedAtMs=25_000,
                confirmedAtMs=36_000,
                detectionSource=StopDetectionSource.COACH,
                alignmentSource=AlignmentSource.COACH_MARK,
                trackedAlignmentDistanceM=30.0,
                createdBy="coach",
            )
        )
    )
    batches.append(
        agg.handle(
            ResolveStopPause(
                clientCommandId="resolve-002",
                sessionId=sid,
                intervalId=f"{sid}-stop-1",
                resumedAtMs=50_000,
            )
        )
    )
    for i, ts in ((1, 70_000), (2, 90_000), (3, 110_000)):
        batches.append(agg.handle(_split(agg, i, ts, "002")))
    clk.set(110_000)
    batches.append(agg.handle(CompleteSession(clientCommandId="complete-002", sessionId=sid)))
    return batches


def build_coach_reset_session_batches() -> list[list[EventEnvelope]]:
    """Coach pacing reset applied at the next wall, then a coach pace target APPLY."""
    agg, clk = _aggregate(golden_workout(_bounded_adaptation()))
    batches: list[list[EventEnvelope]] = []
    batches.append(agg.handle(CreateSession(clientCommandId="create-003", workoutRef="w1")))
    sid = agg.sessionId
    assert sid is not None
    batches.append(agg.handle(ArmSession(clientCommandId="arm-003", sessionId=sid)))
    batches.append(agg.handle(StartSession(clientCommandId="start-003", sessionId=sid)))
    batches.append(agg.handle(_split(agg, 0, 20_000, "003")))
    clk.set(20_000)
    batches.append(
        agg.handle(CoachPacingReset(clientCommandId="reset-003", sessionId=sid, reason="regroup"))
    )
    batches.append(agg.handle(_split(agg, 1, 40_000, "003")))  # reset applies at wall 50 m
    clk.set(40_000)
    batches.append(
        agg.handle(
            ApplyCoachPaceTarget(
                clientCommandId="pace-003",
                sessionId=sid,
                suggestedPaceSecPer100M=82.0,
                currentWallDistanceM=50.0,
            )
        )
    )
    for i, ts in ((2, 60_000), (3, 80_000)):
        batches.append(agg.handle(_split(agg, i, ts, "003")))
    clk.set(80_000)
    batches.append(agg.handle(CompleteSession(clientCommandId="complete-003", sessionId=sid)))
    return batches


GOLDEN_BUILDERS = {
    "normal-session": build_normal_session_batches,
    "stop-pause-session": build_stop_pause_session_batches,
    "coach-reset-session": build_coach_reset_session_batches,
}


def write_golden_journal(name: str, directory: Path) -> Path:
    """Write one golden journal into ``directory`` and return its path."""
    batches = GOLDEN_BUILDERS[name]()
    session_id = batches[0][-1].sessionId
    assert session_id is not None
    path = directory / f"{name}.jsonl"
    log = JsonlSessionEventLog(path, session_id)
    for batch in batches:
        log.append_batch(batch)
    return path


def flatten(batches: list[list[EventEnvelope]]) -> list[EventEnvelope]:
    return [event for batch in batches for event in batch]
