"""Replay StopPause reconstruction tests (Commit 7 §15, §16, §20, §26; ADR-031)."""

from __future__ import annotations

import pytest

from swimcore.replay import ReplayStopPauseError, replay_session
from swimcore.session.state import SessionState
from tests.replay._stream_helpers import SID, StreamBuilder

pytestmark = pytest.mark.replay


def test_retroactive_stop_pause_exact_example() -> None:
    """§15/§26: start=0, stop started=10s, confirmed=20s, resolved=35s.

    wall=35s, stopped=25s, active=10s, elapsed=35s. The StopPause event timestamp (20s) is
    NOT the stop start — the payload ``startedAtMs`` (10s) is.
    """
    b = (
        StreamBuilder()
        .running(0)
        .stop_started(started_at=10_000, confirmed_at=20_000)
        .stop_resolved(started_at=10_000, ended_at=35_000)
    )
    state = replay_session(b.events).state
    assert state.wallDurationMs == 35_000
    assert state.stoppedDurationMs == 25_000
    assert state.activeDurationMs == 10_000
    assert state.elapsedDurationMs == 35_000
    assert state.lifecyclePausedDurationMs == 0
    interval = state.completedStopPauses[0]
    assert (interval.startedAtMs, interval.endedAtMs, interval.durationMs) == (
        10_000,
        35_000,
        25_000,
    )


def test_open_stop_pause_at_horizon() -> None:
    """§14: an open StopPause counts stopStartedAtMs → horizon; lifecycle stays RUNNING."""
    b = StreamBuilder().running(0).stop_started(started_at=10_000, confirmed_at=20_000)
    state = replay_session(b.events).state
    assert state.lifecycleState is SessionState.RUNNING  # StopPause is NOT a lifecycle state
    assert state.openStopPause is not None
    assert state.openStopPause.endedAtMs is None
    assert state.wallDurationMs == 20_000
    assert state.stoppedDurationMs == 10_000  # retroactive: 10s → horizon 20s
    assert state.activeDurationMs == 10_000
    assert state.wallReconciliationPending is True


def test_multiple_non_overlapping_stops() -> None:
    b = StreamBuilder().running(0)
    b.stop_started(started_at=10_000, confirmed_at=21_000, interval_id=f"{SID}-stop-1")
    b.stop_resolved(started_at=10_000, ended_at=30_000, interval_id=f"{SID}-stop-1")
    b.split(0, 40_000)
    b.stop_started(started_at=50_000, confirmed_at=61_000, interval_id=f"{SID}-stop-2")
    b.stop_resolved(started_at=50_000, ended_at=70_000, interval_id=f"{SID}-stop-2")
    state = replay_session(b.events).state
    assert [i.intervalId for i in state.completedStopPauses] == [
        f"{SID}-stop-1",
        f"{SID}-stop-2",
    ]
    assert state.stoppedDurationMs == 20_000 + 20_000
    # intervals never overlap
    first, second = state.completedStopPauses
    assert first.endedAtMs is not None and first.endedAtMs <= second.startedAtMs


def test_overlapping_stop_rejected() -> None:
    b = StreamBuilder().running(0)
    b.stop_started(started_at=10_000, confirmed_at=21_000, interval_id=f"{SID}-stop-1")
    b.stop_resolved(started_at=10_000, ended_at=30_000, interval_id=f"{SID}-stop-1")
    # second stop claims it started BEFORE the first one ended → overlap
    b.stop_started(started_at=25_000, confirmed_at=40_000, interval_id=f"{SID}-stop-2")
    with pytest.raises(ReplayStopPauseError, match="overlap"):
        replay_session(b.events)


def test_second_open_stop_rejected() -> None:
    b = StreamBuilder().running(0)
    b.stop_started(started_at=10_000, confirmed_at=21_000, interval_id=f"{SID}-stop-1")
    b.stop_started(started_at=30_000, confirmed_at=41_000, interval_id=f"{SID}-stop-2")
    with pytest.raises(ReplayStopPauseError, match="already open"):
        replay_session(b.events)


def test_resolve_without_open_rejected() -> None:
    b = StreamBuilder().running(0).stop_resolved(started_at=10_000, ended_at=20_000)
    with pytest.raises(ReplayStopPauseError, match="without an open"):
        replay_session(b.events)


def test_resolve_interval_id_mismatch_rejected() -> None:
    b = StreamBuilder().running(0)
    b.stop_started(started_at=10_000, confirmed_at=21_000, interval_id=f"{SID}-stop-1")
    b.stop_resolved(started_at=10_000, ended_at=30_000, interval_id=f"{SID}-stop-99")
    with pytest.raises(ReplayStopPauseError, match="intervalId"):
        replay_session(b.events)


def test_resolve_started_at_mismatch_rejected() -> None:
    b = StreamBuilder().running(0)
    b.stop_started(started_at=10_000, confirmed_at=21_000)
    b.stop_resolved(started_at=12_000, ended_at=30_000)
    with pytest.raises(ReplayStopPauseError, match="startedAtMs"):
        replay_session(b.events)


def test_pending_wall_reconciliation_survives_resolve_and_closes_at_next_split() -> None:
    """§16: resolve keeps reconciliation pending; the next official split closes it."""
    b = StreamBuilder().running(0)
    b.stop_started(started_at=10_000, confirmed_at=21_000)
    b.stop_resolved(started_at=10_000, ended_at=30_000)
    mid = replay_session(b.events).state
    assert mid.wallReconciliationPending is True  # preserved after resolve
    b.split(0, 45_000)
    closed = replay_session(b.events).state
    assert closed.wallReconciliationPending is False
    assert closed.officialCompletedLengthCount == 1


def test_complete_with_open_stop_rejected() -> None:
    b = StreamBuilder().running(0).stop_started(started_at=10_000, confirmed_at=21_000)
    b.completed(30_000)
    with pytest.raises(ReplayStopPauseError, match="open StopPause"):
        replay_session(b.events)


def test_abort_with_open_stop_counts_stop_to_horizon() -> None:
    b = StreamBuilder().running(0).stop_started(started_at=10_000, confirmed_at=21_000)
    b.aborted(40_000)
    state = replay_session(b.events).state
    assert state.lifecycleState is SessionState.ABORTED
    assert state.openStopPause is not None  # kept as open historical state
    assert state.stoppedDurationMs == 30_000  # 10s → abort horizon 40s
    assert state.activeDurationMs == 10_000


def test_interval_metadata_preserved() -> None:
    b = StreamBuilder().running(0)
    b.stop_started(started_at=10_000, confirmed_at=21_000)
    b.stop_resolved(started_at=10_000, ended_at=30_000)
    interval = replay_session(b.events).state.completedStopPauses[0]
    assert interval.trigger == "MANUAL_INCIDENT"
    assert interval.detectionSource == "COACH"
    assert interval.createdBy == "coach"
    assert interval.wallReconciliationPendingAtResolve is True
