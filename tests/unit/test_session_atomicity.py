"""Command atomicity: a failed command leaves the aggregate unchanged (§2.8)."""

from __future__ import annotations

import copy

import pytest

from contracts.commands import MarkStopPause, RecordSplit
from swimcore.session import InvalidSplitBoundaryError
from tests.unit._session_helpers import record_split, started


def _snapshot(agg) -> dict:
    return {
        "state": agg.state,
        "sessionId": agg.sessionId,
        "appliedPaceTarget": agg.appliedPaceTarget,
        "stop_counter": agg._stop_counter,
        "openStopPause": copy.copy(agg.openStopPause),
        "pending_reset": copy.copy(agg.pendingCoachPacingReset),
        "recorded": dict(agg.recordedSplits),
        "reconciliation_pending": agg._reconciliation_pending,
        "last_wall": agg.lastWallDistanceM,
    }


def test_failed_split_does_not_mutate_state() -> None:
    agg, _ = started()
    before = _snapshot(agg)
    # non-wall distance -> InvalidSplitBoundaryError, atomic
    with pytest.raises(InvalidSplitBoundaryError):
        agg.handle(
            RecordSplit(
                clientCommandId="bad",
                sessionId=agg.sessionId,
                splitId="split-x",
                lengthIndex=0,
                wallTimestampMs=1000,
                source="TOUCHPAD",
                distanceM=13.0,
            )
        )
    assert _snapshot(agg) == before


def test_failed_stop_pause_does_not_increment_counter() -> None:
    agg, _ = started()
    counter_before = agg._stop_counter
    # confirmedAt before stopStartedAt -> ghost.apply_stop_pause rejects before any mutation
    with pytest.raises(Exception):  # noqa: B017 - clock-level InvalidStopIntervalError
        agg.handle(
            MarkStopPause(
                clientCommandId="ms",
                sessionId=agg.sessionId,
                trigger="COACH_STOP",
                stopStartedAtMs=5000,
                confirmedAtMs=1000,
                detectionSource="COACH",
            )
        )
    assert agg._stop_counter == counter_before
    assert agg.openStopPause is None


def test_failed_split_does_not_clear_pending_reconciliation() -> None:
    agg, _ = started()
    # open a StopPause so reconciliation is pending
    agg.handle(
        MarkStopPause(
            clientCommandId="ms",
            sessionId=agg.sessionId,
            trigger="COACH_STOP",
            stopStartedAtMs=1000,
            confirmedAtMs=2000,
            detectionSource="COACH",
            trackedAlignmentDistanceM=10.0,
        )
    )
    assert agg._reconciliation_pending is True
    # a bad split must not clear the pending reconciliation flag
    with pytest.raises(InvalidSplitBoundaryError):
        agg.handle(
            RecordSplit(
                clientCommandId="bad",
                sessionId=agg.sessionId,
                splitId="split-x",
                lengthIndex=0,
                wallTimestampMs=3000,
                source="TOUCHPAD",
                distanceM=13.0,
            )
        )
    assert agg._reconciliation_pending is True


def test_idempotent_replay_returns_same_events_without_mutation() -> None:
    agg, _ = started()
    cmd = record_split(agg, 0)
    first = agg.handle(cmd)
    before = _snapshot(agg)
    again = agg.handle(cmd)  # same clientCommandId + content -> idempotent
    assert [e.eventId for e in first] == [e.eventId for e in again]
    assert _snapshot(agg) == before


def test_failed_create_leaves_aggregate_empty() -> None:
    # An id generator that fails on the 2nd id makes CreateSession fail *after* the first
    # event is built; the aggregate must remain completely uninitialised (2.8).
    from contracts.commands import CreateSession
    from contracts.workout import WorkoutTemplateVersion
    from swimcore.session import FixedClock, SessionAggregate

    class FailingIdGen:
        def __init__(self) -> None:
            self._n = 0

        def next_id(self) -> str:
            self._n += 1
            if self._n >= 2:
                raise RuntimeError("id source exhausted")
            return f"evt-{self._n}"

    wk = WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "w",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 50,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 50, "mode": "even_pace", "targetPaceSecPer100M": 80.0}
                    ],
                }
            ],
        }
    )
    agg = SessionAggregate({"w1": wk}, FixedClock(0), FailingIdGen())
    with pytest.raises(RuntimeError):
        agg.handle(CreateSession(clientCommandId="c", workoutRef="w1"))
    # nothing committed
    assert agg.state is None
    assert agg.sessionId is None
    assert agg.workout is None
    assert agg.paceTimeline is None
    assert agg.appliedPaceTarget is None
    assert agg.poolLengthM is None
