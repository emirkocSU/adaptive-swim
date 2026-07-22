"""Command atomicity: a failed command leaves the aggregate unchanged (§2.8)."""

from __future__ import annotations

import copy

import pytest

from contracts.commands import (
    AbortSession,
    CompleteSession,
    MarkStopPause,
    PauseSession,
    RecordSplit,
    ResolveStopPause,
    ResumeSession,
)
from swimcore.session import InvalidSplitBoundaryError
from swimcore.session.state import SessionState
from tests.unit._session_helpers import record_split, started, workout


class FailingIdGen:
    def __init__(self, start_at: int = 0, fail_at: int = 1) -> None:
        self._n = start_at
        self._fail_at = fail_at

    def next_id(self) -> str:
        self._n += 1
        if self._n == self._fail_at:
            raise RuntimeError("id source exhausted")
        return f"evt-{self._n}"


def _fail_next_event(agg) -> None:
    agg._events._id_gen = FailingIdGen(fail_at=1)


def _fail_second_event(agg) -> None:
    agg._events._id_gen = FailingIdGen(fail_at=2)


def _active_state(agg) -> dict | None:
    clock = agg.activeClock
    return None if clock is None else copy.deepcopy(clock.__dict__)


def _ghost_state(agg) -> dict | None:
    ghost = agg.ghostClock
    if ghost is None:
        return None
    return {
        "state": ghost._state,
        "alignment_active": ghost._alignment_active,
        "wall_reconciliation_pending": ghost._wall_reconciliation_pending,
        "expected_reconciliation_wall": ghost._expected_reconciliation_wall_m,
        "anchor": copy.deepcopy(ghost._anchor),
        "clock": copy.deepcopy(ghost._clock.__dict__),
    }


def _snapshot(agg) -> dict:
    return {
        "state": agg.state,
        "sessionId": agg.sessionId,
        "appliedPaceTarget": agg.appliedPaceTarget,
        "stop_counter": agg._stop_counter,
        "openStopPause": copy.copy(agg.openStopPause),
        "pending_reset": copy.copy(agg.pendingCoachPacingReset),
        "recorded": dict(agg.recordedSplits),
        "recorded_by_id": dict(agg.recordedSplitsById),
        "split_id_by_length": dict(agg.splitIdByLengthIndex),
        "verified": dict(agg.verifiedSplits),
        "reconciliation_pending": agg._reconciliation_pending,
        "expected_reconciliation_wall": agg._expected_reconciliation_wall_m,
        "pause_started": agg._pause_started_at_ms,
        "pause_offset": agg._pause_offset_ms,
        "last_wall": agg.lastWallDistanceM,
        "event_checkpoint": agg._events.checkpoint(),
        "ghost": _ghost_state(agg),
        "active": _active_state(agg),
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


def test_failed_record_split_event_creation_rolls_back_split_state() -> None:
    agg, _ = started()
    before = _snapshot(agg)
    _fail_next_event(agg)

    with pytest.raises(RuntimeError):
        agg.handle(record_split(agg, 0))

    assert _snapshot(agg) == before


def test_failed_mark_stop_pause_event_creation_rolls_back_all_stop_state() -> None:
    agg, _ = started()
    before = _snapshot(agg)
    _fail_next_event(agg)

    with pytest.raises(RuntimeError):
        agg.handle(
            MarkStopPause(
                clientCommandId="ms-event-fails",
                sessionId=agg.sessionId,
                trigger="COACH_STOP",
                stopStartedAtMs=1000,
                confirmedAtMs=2000,
                detectionSource="COACH",
                trackedAlignmentDistanceM=10.0,
            )
        )

    assert _snapshot(agg) == before


def test_failed_multi_event_mark_stop_pause_rolls_back_after_first_event() -> None:
    agg, _ = started()
    before = _snapshot(agg)
    _fail_second_event(agg)

    with pytest.raises(RuntimeError):
        agg.handle(
            MarkStopPause(
                clientCommandId="ms-second-event-fails",
                sessionId=agg.sessionId,
                trigger="SENSOR_STOP",
                stopStartedAtMs=1000,
                confirmedAtMs=2000,
                detectionSource="SENSOR",
                trackedAlignmentDistanceM=10.0,
            )
        )

    assert _snapshot(agg) == before


def test_failed_resolve_stop_pause_event_creation_restores_open_stop() -> None:
    agg, _ = started()
    agg.handle(
        MarkStopPause(
            clientCommandId="ms-open",
            sessionId=agg.sessionId,
            trigger="COACH_STOP",
            stopStartedAtMs=1000,
            confirmedAtMs=2000,
            detectionSource="COACH",
            trackedAlignmentDistanceM=10.0,
        )
    )
    assert agg.openStopPause is not None
    interval_id = agg.openStopPause.intervalId
    before = _snapshot(agg)
    _fail_next_event(agg)

    with pytest.raises(RuntimeError):
        agg.handle(
            ResolveStopPause(
                clientCommandId="resolve-fails",
                sessionId=agg.sessionId,
                intervalId=interval_id,
                resumedAtMs=3000,
            )
        )

    assert _snapshot(agg) == before


def test_failed_pause_event_creation_keeps_running_state() -> None:
    agg, _ = started()
    before = _snapshot(agg)
    _fail_next_event(agg)

    with pytest.raises(RuntimeError):
        agg.handle(PauseSession(clientCommandId="pause-fails", sessionId=agg.sessionId))

    assert agg.state is SessionState.RUNNING
    assert _snapshot(agg) == before


def test_failed_resume_event_creation_restores_pause_bookkeeping() -> None:
    agg, clk = started()
    clk.set(1000)
    agg.handle(PauseSession(clientCommandId="pause-ok", sessionId=agg.sessionId))
    clk.set(2000)
    before = _snapshot(agg)
    _fail_next_event(agg)

    with pytest.raises(RuntimeError):
        agg.handle(ResumeSession(clientCommandId="resume-fails", sessionId=agg.sessionId))

    assert _snapshot(agg) == before


def test_failed_complete_event_creation_keeps_session_running() -> None:
    agg, clk = started(workout(reps=1, dist=100))
    for i in range(4):
        agg.handle(record_split(agg, i))
    clk.set(200000)
    before = _snapshot(agg)
    _fail_next_event(agg)

    with pytest.raises(RuntimeError):
        agg.handle(CompleteSession(clientCommandId="complete-fails", sessionId=agg.sessionId))

    assert agg.state is SessionState.RUNNING
    assert _snapshot(agg) == before


def test_failed_abort_event_creation_preserves_open_and_pending_state() -> None:
    agg, clk = started()
    agg.handle(
        MarkStopPause(
            clientCommandId="ms-before-abort",
            sessionId=agg.sessionId,
            trigger="COACH_STOP",
            stopStartedAtMs=1000,
            confirmedAtMs=2000,
            detectionSource="COACH",
            trackedAlignmentDistanceM=10.0,
        )
    )
    clk.set(3000)
    before = _snapshot(agg)
    _fail_next_event(agg)

    with pytest.raises(RuntimeError):
        agg.handle(AbortSession(clientCommandId="abort-fails", sessionId=agg.sessionId))

    assert _snapshot(agg) == before


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


def test_failed_command_preserves_runtime_reference_graph() -> None:
    """Rollback preserves both values and the authoritative object identities."""
    agg, _ = started()
    active_before = agg.activeClock
    ghost_before = agg.ghostClock
    timeline_before = agg.paceTimeline
    assert active_before is not None
    assert ghost_before is not None
    assert timeline_before is not None
    assert ghost_before.is_bound_to(
        active_clock=active_before,
        timeline=timeline_before,
    )
    active_state_before = copy.deepcopy(active_before.__dict__)
    ghost_state_before = _ghost_state(agg)

    with pytest.raises(InvalidSplitBoundaryError):
        agg.handle(
            RecordSplit(
                clientCommandId="bad-reference-graph",
                sessionId=agg.sessionId,
                splitId="split-reference-graph",
                lengthIndex=0,
                wallTimestampMs=1000,
                source="TOUCHPAD",
                distanceM=13.0,
            )
        )

    assert agg.activeClock is active_before
    assert agg.ghostClock is ghost_before
    assert agg.paceTimeline is timeline_before
    assert ghost_before.is_bound_to(
        active_clock=active_before,
        timeline=timeline_before,
    )
    assert active_before.__dict__ == active_state_before
    assert _ghost_state(agg) == ghost_state_before
