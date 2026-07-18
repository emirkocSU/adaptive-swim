"""Commit 6 — StopPause orchestration."""

from __future__ import annotations

import pytest

from contracts.commands import MarkStopPause, ResolveStopPause
from swimcore.ghost import GhostState
from swimcore.session import (
    SessionState,
    StopPauseAlreadyOpenError,
    StopPauseIntervalMismatchError,
)
from swimcore.session.errors import InvalidSessionTransitionError
from tests.unit._session_helpers import record_split, started


def _mark(agg, cid="s1", trigger="COACH_STOP", start=10000, confirm=20000, tracked=48.0):
    return agg.handle(
        MarkStopPause(
            clientCommandId=cid,
            sessionId=agg.sessionId,
            trigger=trigger,
            stopStartedAtMs=start,
            confirmedAtMs=confirm,
            detectionSource="COACH",
            trackedAlignmentDistanceM=tracked,
        )
    )


def _interval_id(agg, cid="s1"):
    return agg.processedClientCommandIds[cid][1][-1].payload.intervalId


def test_mark_stop_pause_only_in_running() -> None:
    agg, clk = started()
    agg.handle(
        __import__("contracts.commands", fromlist=["PauseSession"]).PauseSession(
            clientCommandId="p", sessionId=agg.sessionId
        )
    )
    with pytest.raises(InvalidSessionTransitionError):
        _mark(agg)


def test_session_remains_running_during_stop_pause() -> None:
    agg, clk = started()
    _mark(agg)
    assert agg.state is SessionState.RUNNING
    assert agg.ghostClock.snapshot(agg._eff(20000)).state is GhostState.STOP_PAUSED


def test_retroactive_active_time_correction() -> None:
    agg, clk = started()
    # active clock started at 200; observe up to 15200 then stop began at 10200
    _mark(agg, start=10200, confirm=20200)
    snap = agg.ghostClock.snapshot(agg._eff(20200))
    assert snap.activeElapsedMs == 10000  # (10200-200) frozen retroactively
    assert snap.stoppedElapsedMs == 10000


def test_ghost_enters_stop_paused_and_resolve_resumes() -> None:
    agg, clk = started()
    _mark(agg)
    iid = _interval_id(agg)
    agg.handle(
        ResolveStopPause(
            clientCommandId="r", sessionId=agg.sessionId, intervalId=iid, resumedAtMs=20000
        )
    )
    assert agg.ghostClock.snapshot(agg._eff(20000)).state is GhostState.ACTIVE
    assert agg.openStopPause is None


def test_interval_id_mismatch_rejected() -> None:
    agg, clk = started()
    _mark(agg)
    with pytest.raises(StopPauseIntervalMismatchError):
        agg.handle(
            ResolveStopPause(
                clientCommandId="r", sessionId=agg.sessionId, intervalId="wrong", resumedAtMs=20000
            )
        )


def test_second_open_stop_pause_rejected() -> None:
    agg, clk = started()
    _mark(agg)
    with pytest.raises(StopPauseAlreadyOpenError):
        _mark(agg, cid="s2", start=21000, confirm=22000)


def test_overlapping_stop_pause_rejected() -> None:
    from swimcore.time import InvalidStopIntervalError

    agg, clk = started()
    _mark(agg, start=10000, confirm=20000, tracked=23.0)  # expected wall 25 = length 0
    agg.handle(
        ResolveStopPause(
            clientCommandId="r",
            sessionId=agg.sessionId,
            intervalId=_interval_id(agg),
            resumedAtMs=22000,
        )
    )
    agg.handle(record_split(agg, 0, ts=30000))  # reconcile at length 0
    with pytest.raises(InvalidStopIntervalError):
        _mark(agg, cid="s2", start=21000, confirm=35000, tracked=48.0)


def test_split_at_expected_wall_reconciles_pending_alignment() -> None:
    agg, clk = started()
    _mark(agg, tracked=23.0)  # expected wall 25 = official length 0
    agg.handle(
        ResolveStopPause(
            clientCommandId="r",
            sessionId=agg.sessionId,
            intervalId=_interval_id(agg),
            resumedAtMs=20000,
        )
    )
    agg.handle(record_split(agg, 0, ts=25000))
    assert agg._reconciliation_pending is False


def test_wrong_wall_split_does_not_reconcile() -> None:
    agg, clk = started()
    _mark(agg, tracked=48.0)  # expected wall 50 = official length 1
    agg.handle(
        ResolveStopPause(
            clientCommandId="r",
            sessionId=agg.sessionId,
            intervalId=_interval_id(agg),
            resumedAtMs=20000,
        )
    )
    # recording the earlier length-0 wall (25 m) must not reconcile; pending stays True
    agg.handle(record_split(agg, 0, ts=25000))
    assert agg._reconciliation_pending is True
