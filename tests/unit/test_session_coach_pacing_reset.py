"""Commit 6 — coach pacing reset (not a StopPause; applied only at the next wall)."""

from __future__ import annotations

import pytest

from contracts.commands import CoachPacingReset
from swimcore.session import PacingResetAlreadyPendingError, SessionState
from tests.unit._session_helpers import record_split, started


def _reset(agg, cid="r1", reason="regroup"):
    return agg.handle(CoachPacingReset(clientCommandId=cid, sessionId=agg.sessionId, reason=reason))


def test_request_does_not_stop_clock_or_change_state() -> None:
    agg, clk = started()
    active_before = agg.activeClock.active_elapsed_ms(agg._eff(30000))
    ev = _reset(agg)
    assert ev[-1].type.value == "CoachPacingResetRequested"
    assert agg.state is SessionState.RUNNING
    assert agg.activeClock.active_elapsed_ms(agg._eff(31000)) >= active_before


def test_request_does_not_apply_mid_length() -> None:
    agg, clk = started()
    _reset(agg)
    assert agg.pendingCoachPacingReset is not None  # still pending, not applied


def test_applied_only_at_next_valid_wall() -> None:
    agg, clk = started()
    _reset(agg)
    ev = agg.handle(record_split(agg, 0, ts=40000, cid="s0"))
    types = [e.type.value for e in ev]
    assert "CoachPacingResetApplied" in types
    assert "SplitRecorded" in types
    assert agg.pendingCoachPacingReset is None


def test_second_conflicting_pending_reset_rejected() -> None:
    agg, clk = started()
    _reset(agg, cid="r1", reason="a")
    with pytest.raises(PacingResetAlreadyPendingError):
        _reset(agg, cid="r2", reason="b")


def test_requested_and_applied_events_generated() -> None:
    agg, clk = started()
    req = _reset(agg)
    applied = agg.handle(record_split(agg, 0, ts=40000, cid="s0"))
    assert req[0].type.value == "CoachPacingResetRequested"
    assert applied[0].type.value == "CoachPacingResetApplied"


def test_reset_does_not_erase_previous_splits() -> None:
    agg, clk = started()
    agg.handle(record_split(agg, 0, ts=40000, cid="s0"))
    clk.set(41000)
    _reset(agg)
    agg.handle(record_split(agg, 1, ts=80000, cid="s1"))
    assert 0 in agg.recordedSplits and 1 in agg.recordedSplits
