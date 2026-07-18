"""Commit 6 — property-based invariants + atomicity."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from contracts.commands import (
    AbortSession,
    ApplyCoachPaceTarget,
    ArmSession,
    CompleteSession,
    CreateSession,
    MarkStopPause,
    StartSession,
)
from swimcore.session import SessionState
from tests.unit._session_helpers import (
    bounded_adaptation,
    new_aggregate,
    record_split,
    started,
    workout,
)


# --------------------------------------------------------------------------- properties
def test_event_seq_strictly_increasing_over_run() -> None:
    agg, clk = started()
    events = []
    for i in range(5):
        events += agg.handle(record_split(agg, i, ts=40000 * (i + 1), cid=f"s{i}"))
    seqs = [e.seq for e in events]
    assert all(b - a == 1 for a, b in zip(seqs, seqs[1:], strict=False)) or seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


@given(cid=st.text(min_size=1, max_size=8))
def test_duplicate_commands_do_not_change_state(cid: str) -> None:
    agg, clk = new_aggregate()
    agg.handle(CreateSession(clientCommandId=cid, workoutRef="w1"))
    state_after = agg.state
    splits_after = dict(agg.recordedSplits)
    agg.handle(CreateSession(clientCommandId=cid, workoutRef="w1"))
    assert agg.state == state_after
    assert agg.recordedSplits == splits_after


def test_terminal_states_never_transition() -> None:
    from swimcore.session import InvalidSessionTransitionError

    agg, clk = started()
    agg.handle(AbortSession(clientCommandId="a", sessionId=agg.sessionId))
    assert agg.state is SessionState.ABORTED
    for cmd in (
        ArmSession(clientCommandId="x1", sessionId=agg.sessionId),
        StartSession(clientCommandId="x2", sessionId=agg.sessionId),
        CompleteSession(clientCommandId="x3", sessionId=agg.sessionId),
    ):
        with pytest.raises(InvalidSessionTransitionError):
            agg.handle(cmd)


def test_same_command_sequence_gives_identical_state_and_events() -> None:
    def run() -> list[str]:
        agg, clk = started()
        ev = agg.handle(record_split(agg, 0, ts=40000, cid="s0"))
        return [f"{e.seq}:{e.type.value}" for e in ev]

    assert run() == run()


@given(suggested=st.floats(min_value=40.0, max_value=200.0, allow_nan=False, allow_infinity=False))
def test_applied_pace_always_within_safety_bounds(suggested: float) -> None:
    agg, clk = started(workout(adaptation=bounded_adaptation()))
    agg.handle(
        ApplyCoachPaceTarget(
            clientCommandId="p",
            sessionId=agg.sessionId,
            suggestedPaceSecPer100M=suggested,
            isWallBoundary=True,
            currentWallDistanceM=100.0,
            confidence=0.9,
            dataQuality=0.9,
        )
    )
    # fastest 76, slowest 90 → applied target always inside
    assert 76.0 - 1e-6 <= agg.appliedPaceTarget <= 90.0 + 1e-6


def test_active_plus_stopped_equals_wall_during_stop() -> None:
    agg, clk = started()
    agg.handle(
        MarkStopPause(
            clientCommandId="st",
            sessionId=agg.sessionId,
            trigger="COACH_STOP",
            stopStartedAtMs=10000,
            confirmedAtMs=20000,
            detectionSource="COACH",
            trackedAlignmentDistanceM=48.0,
        )
    )
    snap = agg.ghostClock.snapshot(agg._eff(20000))
    assert snap.wallElapsedMs == snap.activeElapsedMs + snap.stoppedElapsedMs


def test_session_stays_running_during_stop_pause_property() -> None:
    agg, clk = started()
    agg.handle(
        MarkStopPause(
            clientCommandId="st",
            sessionId=agg.sessionId,
            trigger="SENSOR_STOP",
            stopStartedAtMs=10000,
            confirmedAtMs=20000,
            detectionSource="SENSOR",
            trackedAlignmentDistanceM=48.0,
        )
    )
    assert agg.state is SessionState.RUNNING


# --------------------------------------------------------------------------- atomicity
def test_failed_command_leaves_aggregate_unchanged() -> None:
    from swimcore.session import InvalidSessionTransitionError

    agg, clk = started()
    before_state = agg.state
    before_seq = agg._events._seq
    before_processed = dict(agg.processedClientCommandIds)
    with pytest.raises(InvalidSessionTransitionError):
        agg.handle(ArmSession(clientCommandId="bad", sessionId=agg.sessionId))
    assert agg.state == before_state
    assert agg._events._seq == before_seq
    assert "bad" not in agg.processedClientCommandIds
    assert agg.processedClientCommandIds.keys() == before_processed.keys()


def test_failed_ghost_alignment_does_not_freeze_active_clock() -> None:
    from swimcore.ghost import InvalidAlignmentDistanceError

    agg, clk = started()
    with pytest.raises(InvalidAlignmentDistanceError):
        agg.handle(
            MarkStopPause(
                clientCommandId="st",
                sessionId=agg.sessionId,
                trigger="COACH_STOP",
                stopStartedAtMs=10000,
                confirmedAtMs=20000,
                detectionSource="COACH",
                trackedAlignmentDistanceM=99999.0,
            )
        )
    assert agg.activeClock.is_frozen is False
    assert agg.openStopPause is None


def test_failed_pace_decision_does_not_change_applied_target() -> None:
    agg, clk = started(workout(adaptation=bounded_adaptation()))
    before = agg.appliedPaceTarget
    # low confidence → ABSTAIN_USE_COACH_PLAN → applied target unchanged
    agg.handle(
        ApplyCoachPaceTarget(
            clientCommandId="p",
            sessionId=agg.sessionId,
            suggestedPaceSecPer100M=82.0,
            source="ML",
            isWallBoundary=True,
            confidence=0.05,
            dataQuality=0.9,
        )
    )
    assert agg.appliedPaceTarget == before


def test_failed_reconciliation_leaves_pending_intact() -> None:

    agg, clk = started()
    agg.handle(
        MarkStopPause(
            clientCommandId="st",
            sessionId=agg.sessionId,
            trigger="COACH_STOP",
            stopStartedAtMs=10000,
            confirmedAtMs=20000,
            detectionSource="COACH",
            trackedAlignmentDistanceM=48.0,
        )
    )
    from contracts.commands import ResolveStopPause

    agg.handle(
        ResolveStopPause(
            clientCommandId="r",
            sessionId=agg.sessionId,
            intervalId=agg.processedClientCommandIds["st"][1][-1].payload.intervalId,
            resumedAtMs=20000,
        )
    )
    # length-0 (25 m) records but does NOT reconcile the pending 50 m wall; pending intact
    agg.handle(record_split(agg, 0, ts=70000, cid="sp"))
    assert agg._reconciliation_pending is True
