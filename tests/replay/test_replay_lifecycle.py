"""Replay lifecycle reconstruction tests (Commit 7 §14, §16, §20, §26)."""

from __future__ import annotations

import pytest

from swimcore.replay import (
    EmptyReplayError,
    ReplayStopPauseError,
    ReplayTransitionError,
    replay_session,
)
from swimcore.session.state import SessionState
from tests.replay._stream_helpers import StreamBuilder

pytestmark = pytest.mark.replay


def test_empty_stream_raises_documented_error() -> None:
    with pytest.raises(EmptyReplayError):
        replay_session([])


def test_normal_lifecycle() -> None:
    b = StreamBuilder().running(0)
    for i, ts in enumerate((20_000, 40_000, 60_000, 80_000)):
        b.split(i, ts)
    b.completed(80_000)
    state = replay_session(b.events).state
    assert state.lifecycleState is SessionState.COMPLETED
    assert state.startedAtMs == 0 and state.endedAtMs == 80_000
    assert state.wallDurationMs == state.elapsedDurationMs == state.activeDurationMs == 80_000
    assert state.stoppedDurationMs == 0 and state.lifecyclePausedDurationMs == 0
    assert state.lastSeq == b.events[-1].seq
    assert state.lastEventTimestampMs == 80_000
    assert state.processedClientCommandIds == tuple(
        dict.fromkeys(e.clientCommandId for e in b.events if e.clientCommandId)
    )


def test_lifecycle_pause_resume_durations_exact_example() -> None:
    """§26: start=0, pause=10s, resume=20s, complete=40s."""
    b = StreamBuilder().running(0).paused(10_000).resumed(20_000).completed(40_000)
    state = replay_session(b.events).state
    assert state.wallDurationMs == 40_000
    assert state.lifecyclePausedDurationMs == 10_000
    assert state.elapsedDurationMs == 30_000
    assert state.stoppedDurationMs == 0
    assert state.activeDurationMs == 30_000


def test_open_lifecycle_pause_counts_to_horizon() -> None:
    b = StreamBuilder().running(0).paused(10_000)
    state = replay_session(b.events).state
    assert state.lifecycleState is SessionState.PAUSED
    assert state.wallDurationMs == 10_000
    assert state.lifecyclePausedDurationMs == 0  # pause started AT the horizon
    # Aborting later moves the horizon: the open pause interval runs to the abort time.
    b3 = StreamBuilder().running(0).paused(10_000).aborted(25_000)
    state3 = replay_session(b3.events).state
    assert state3.lifecyclePausedDurationMs == 15_000
    assert state3.activeDurationMs == 10_000
    assert state3.wallDurationMs == 25_000


def test_abort_paths_from_every_state() -> None:
    created = StreamBuilder().created(0).aborted(1_000)
    assert replay_session(created.events).state.lifecycleState is SessionState.ABORTED

    armed = StreamBuilder().created(0).armed(0).aborted(1_000)
    assert replay_session(armed.events).state.lifecycleState is SessionState.ABORTED

    running = StreamBuilder().running(0).aborted(5_000)
    state = replay_session(running.events).state
    assert state.lifecycleState is SessionState.ABORTED
    assert state.endedAtMs == 5_000 and state.wallDurationMs == 5_000

    paused = StreamBuilder().running(0).paused(2_000).aborted(5_000)
    state_p = replay_session(paused.events).state
    assert state_p.lifecycleState is SessionState.ABORTED
    assert state_p.lifecyclePausedDurationMs == 3_000
    assert state_p.activeDurationMs == 2_000


def test_invalid_transition_rejected() -> None:
    skipped_arm = StreamBuilder().created(0).started(0)
    with pytest.raises(ReplayTransitionError):
        replay_session(skipped_arm.events)

    resume_without_pause = StreamBuilder().running(0).resumed(5_000)
    with pytest.raises(ReplayTransitionError):
        replay_session(resume_without_pause.events)

    double_create = StreamBuilder().created(0).created(0)
    with pytest.raises(ReplayTransitionError):
        replay_session(double_create.events)


def test_terminal_event_protection() -> None:
    after_complete = StreamBuilder().running(0)
    for i, ts in enumerate((10_000,)):
        after_complete.split(i, ts)
    after_complete.completed(10_000).split(1, 20_000)
    with pytest.raises(ReplayTransitionError, match="terminal"):
        replay_session(after_complete.events)

    after_abort = StreamBuilder().running(0).aborted(1_000).armed(2_000)
    with pytest.raises(ReplayTransitionError, match="terminal"):
        replay_session(after_abort.events)


def test_split_before_running_rejected() -> None:
    b = StreamBuilder().created(0).armed(0).split(0, 1_000)
    with pytest.raises(ReplayTransitionError, match="RUNNING"):
        replay_session(b.events)


def test_complete_before_running_rejected() -> None:
    b = StreamBuilder().created(0).armed(0).completed(1_000)
    with pytest.raises(ReplayTransitionError):
        replay_session(b.events)


def test_event_before_session_created_rejected() -> None:
    b = StreamBuilder()
    b.armed(0)
    with pytest.raises(ReplayTransitionError, match="before SessionCreated"):
        replay_session(b.events)


def test_pause_with_open_stop_is_corruption() -> None:
    b = (
        StreamBuilder()
        .running(0)
        .stop_started(started_at=5_000, confirmed_at=16_000)
        .paused(20_000)
    )
    with pytest.raises(ReplayStopPauseError, match="corrupt"):
        replay_session(b.events)


def test_replay_is_deterministic_same_events_same_state() -> None:
    b = StreamBuilder().running(0)
    b.split(0, 20_000).paused(30_000).resumed(40_000).split(1, 60_000)
    first = replay_session(b.events)
    second = replay_session(b.events)
    assert first == second
    assert first.state == second.state
