"""Commit 6 correction invariants (sections 2.1–2.13)."""

from __future__ import annotations

import pytest

from contracts.commands import (
    ApplyCoachPaceTarget,
    ArmSession,
    CompleteSession,
    MarkStopPause,
    PauseSession,
    ResolveStopPause,
    ResumeSession,
)
from swimcore.ghost import GhostState
from swimcore.session import (
    SessionState,
    StopPauseAlreadyOpenError,
)
from swimcore.session.errors import (
    InvalidEventTimeError,
    SessionIdMismatchError,
    WorkoutNotCompletedError,
)
from swimcore.session.handler import EventFactory, SequenceIdGenerator
from tests.unit._session_helpers import record_split, started, workout


def _mark(
    agg,
    cid="st",
    start=10000,
    confirm=20000,
    tracked=23.0,
    trigger="SENSOR_STOP",
    src="SENSOR",
    quality="HIGH",
):
    return agg.handle(
        MarkStopPause(
            clientCommandId=cid,
            sessionId=agg.sessionId,
            trigger=trigger,
            stopStartedAtMs=start,
            confirmedAtMs=confirm,
            detectionSource=src,
            detectionQuality=quality,
            alignmentSource="TRACKED_POSITION",
            alignmentQuality="HIGH",
            stopStartTimeQuality="HIGH",
            trackedAlignmentDistanceM=tracked,
            createdBy="sensor",
        )
    )


# --------------------------------------------------------------------------- 2.1 session identity
@pytest.mark.parametrize(
    "cmd_factory",
    [
        lambda a: ArmSession(clientCommandId="x", sessionId="WRONG"),
        lambda a: PauseSession(clientCommandId="x", sessionId="WRONG"),
        lambda a: ApplyCoachPaceTarget(
            clientCommandId="x", sessionId="WRONG", suggestedPaceSecPer100M=80.0
        ),
    ],
)
def test_commands_reject_other_session_id(cmd_factory) -> None:
    agg, clk = started()
    with pytest.raises(SessionIdMismatchError):
        agg.handle(cmd_factory(agg))


def test_split_rejects_other_session_id() -> None:
    from contracts.commands import RecordSplit

    agg, clk = started()
    with pytest.raises(SessionIdMismatchError):
        agg.handle(
            RecordSplit(
                clientCommandId="x",
                sessionId="WRONG",
                splitId="s",
                lengthIndex=0,
                wallTimestampMs=40000,
                source="TOUCHPAD",
                distanceM=25.0,
            )
        )


def test_stop_pause_rejects_other_session_id() -> None:
    agg, clk = started()
    with pytest.raises(SessionIdMismatchError):
        agg.handle(
            MarkStopPause(
                clientCommandId="x",
                sessionId="WRONG",
                trigger="COACH_STOP",
                stopStartedAtMs=1,
                confirmedAtMs=2,
                detectionSource="COACH",
                trackedAlignmentDistanceM=0.0,
            )
        )


# --------------------------------------------------------------------------- 2.2 completion
def test_complete_rejected_without_splits() -> None:
    agg, clk = started(workout(reps=2, dist=25))  # expected 2 length splits
    clk.set(90000)
    with pytest.raises(WorkoutNotCompletedError):
        agg.handle(CompleteSession(clientCommandId="c", sessionId=agg.sessionId))


def test_complete_rejected_before_final_wall() -> None:
    agg, clk = started(workout(reps=2, dist=25))
    agg.handle(record_split(agg, 0, ts=40000))
    clk.set(90000)
    with pytest.raises(WorkoutNotCompletedError):
        agg.handle(CompleteSession(clientCommandId="c", sessionId=agg.sessionId))


def test_complete_succeeds_only_after_exact_final_wall() -> None:
    agg, clk = started(workout(reps=2, dist=25))
    agg.handle(record_split(agg, 0, ts=40000))
    agg.handle(record_split(agg, 1, ts=80000))
    clk.set(90000)
    agg.handle(CompleteSession(clientCommandId="c", sessionId=agg.sessionId))
    assert agg.state is SessionState.COMPLETED


# --------------------------------------------------------------------------- 2.6 ghost anchor
def test_coach_reset_changes_display_anchor_at_wall() -> None:
    from contracts.commands import CoachPacingReset

    agg, clk = started()
    clk.set(30000)
    agg.handle(CoachPacingReset(clientCommandId="r", sessionId=agg.sessionId, reason="x"))
    agg.handle(record_split(agg, 0, ts=40000))  # expected wall 25 → applies
    snap = agg.ghostClock.snapshot(agg._eff(40000))
    assert snap.displayDistanceM == pytest.approx(25.0)
    assert snap.state is GhostState.ACTIVE  # no StopPause created


def test_coach_reset_rejected_mid_pool() -> None:
    from swimcore.ghost import InvalidWallReconciliationError

    agg, clk = started()
    with pytest.raises(InvalidWallReconciliationError):
        agg.ghostClock.apply_coach_pacing_reset_at_wall(13.0, agg._eff(30000))


# --------------------------------------------------------------------------- 2.7 lifecycle pause
def test_ghost_and_active_time_do_not_advance_while_session_paused() -> None:
    agg, clk = started()
    clk.set(30000)
    agg.handle(PauseSession(clientCommandId="p", sessionId=agg.sessionId))
    d1 = agg.ghostClock.snapshot(agg._eff(30000)).displayDistanceM
    a1 = agg.activeClock.active_elapsed_ms(agg._eff(30000))
    # later real time while paused → effective runtime pinned
    d2 = agg.ghostClock.snapshot(agg._eff(90000)).displayDistanceM
    a2 = agg.activeClock.active_elapsed_ms(agg._eff(90000))
    assert d1 == d2 and a1 == a2


def test_resume_does_not_rewind_effective_time() -> None:
    agg, clk = started()
    clk.set(30000)
    agg.handle(PauseSession(clientCommandId="p", sessionId=agg.sessionId))
    clk.set(60000)
    agg.handle(ResumeSession(clientCommandId="r", sessionId=agg.sessionId))
    # effective active time continues from pause point (30 s of real running before pause)
    assert agg.activeClock.active_elapsed_ms(agg._eff(70000)) >= 30000 - 1


def test_pause_rejected_while_stop_pause_open() -> None:
    agg, clk = started()
    _mark(agg)
    with pytest.raises(StopPauseAlreadyOpenError):
        agg.handle(PauseSession(clientCommandId="p", sessionId=agg.sessionId))


# --------------------------------------------------------------------------- 2.8 atomicity
def test_failed_stop_pause_does_not_increment_counter() -> None:
    from swimcore.ghost import InvalidAlignmentDistanceError

    agg, clk = started()
    before = agg._stop_counter
    with pytest.raises(InvalidAlignmentDistanceError):
        _mark(agg, tracked=999999.0)
    assert agg._stop_counter == before
    assert agg.openStopPause is None
    assert agg.activeClock.is_frozen is False


# --------------------------------------------------------------------------- 2.9 event factory time
def test_event_factory_rejects_historical_timestamp() -> None:
    from contracts.enums import EventType
    from contracts.events import SessionArmedPayload

    f = EventFactory(SequenceIdGenerator())
    f.build(EventType.SessionArmed, SessionArmedPayload(sessionId="s"), 1000, "s", "c1")
    with pytest.raises(InvalidEventTimeError):
        f.build(EventType.SessionArmed, SessionArmedPayload(sessionId="s"), 500, "s", "c2")


def test_event_factory_does_not_clamp_time() -> None:
    from contracts.enums import EventType
    from contracts.events import SessionArmedPayload

    f = EventFactory(SequenceIdGenerator())
    e = f.build(EventType.SessionArmed, SessionArmedPayload(sessionId="s"), 1000, "s", "c1")
    assert e.tsMs == 1000  # exact, not clamped/advanced


def test_event_batch_allows_same_timestamp() -> None:
    from contracts.enums import EventType
    from contracts.events import SessionArmedPayload, SessionStartedPayload

    f = EventFactory(SequenceIdGenerator())
    events = f.build_batch(
        [
            (EventType.SessionArmed, SessionArmedPayload(sessionId="s"), 1000),
            (
                EventType.SessionStarted,
                SessionStartedPayload(sessionId="s", startedAtMs=1000),
                1000,
            ),
        ],
        "s",
        "c1",
    )
    assert [e.tsMs for e in events] == [1000, 1000]
    assert [e.seq for e in events] == [1, 2]


def test_retroactive_stop_keeps_start_in_payload() -> None:
    agg, clk = started()
    ev = _mark(agg, start=10000, confirm=20000, trigger="SENSOR_STOP")
    started_evt = next(e for e in ev if e.type.value == "StopPauseStarted")
    assert started_evt.tsMs == 20000  # confirmation time
    assert started_evt.payload.startedAtMs == 10000  # real stop start preserved


# --------------------------------------------------------------------------- 2.13 metadata preserved
def test_stop_pause_resolution_preserves_sensor_metadata() -> None:
    agg, clk = started()
    _mark(agg, tracked=23.0, trigger="SENSOR_STOP", src="SENSOR", quality="HIGH")
    iid = agg.processedClientCommandIds["st"][1][-1].payload.intervalId
    ev = agg.handle(
        ResolveStopPause(
            clientCommandId="r",
            sessionId=agg.sessionId,
            intervalId=iid,
            resumedAtMs=20000,
            resolvedBy="coach",
        )
    )
    resolved = ev[-1].payload
    assert resolved.detectionSource.value == "SENSOR"  # not overwritten to COACH
    assert resolved.detectionQuality.value == "HIGH"
    assert resolved.trigger.value == "SENSOR_STOP"
