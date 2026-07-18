"""Commit 6 — session lifecycle transitions."""

from __future__ import annotations

import pytest

from contracts.commands import (
    AbortSession,
    ArmSession,
    CompleteSession,
    CreateSession,
    StartSession,
)
from swimcore.session import InvalidSessionTransitionError, SessionState
from tests.unit._session_helpers import new_aggregate, record_split, started, workout


def test_create_arm_start_complete() -> None:
    # a single-length workout so completion is reachable in the test
    agg, clk = started(workout(reps=1, dist=25))
    assert agg.state is SessionState.RUNNING
    agg.handle(record_split(agg, 0, ts=40000))
    clk.set(50000)
    agg.handle(CompleteSession(clientCommandId="done", sessionId=agg.sessionId))
    assert agg.state is SessionState.COMPLETED


def test_terminal_state_rejects_commands() -> None:
    agg, clk = started()
    agg.handle(AbortSession(clientCommandId="ab", sessionId=agg.sessionId))
    assert agg.state is SessionState.ABORTED
    with pytest.raises(InvalidSessionTransitionError):
        agg.handle(ArmSession(clientCommandId="a", sessionId=agg.sessionId))


def test_create_then_abort() -> None:
    agg, clk = new_aggregate()
    agg.handle(CreateSession(clientCommandId="c", workoutRef="w1"))
    agg.handle(AbortSession(clientCommandId="a", sessionId=agg.sessionId))
    assert agg.state is SessionState.ABORTED


def test_armed_abort() -> None:
    agg, clk = new_aggregate()
    agg.handle(CreateSession(clientCommandId="c", workoutRef="w1"))
    agg.handle(ArmSession(clientCommandId="arm", sessionId=agg.sessionId))
    agg.handle(AbortSession(clientCommandId="a", sessionId=agg.sessionId))
    assert agg.state is SessionState.ABORTED


def test_running_abort() -> None:
    agg, clk = started()
    agg.handle(AbortSession(clientCommandId="a", sessionId=agg.sessionId))
    assert agg.state is SessionState.ABORTED


def test_invalid_start_before_arm() -> None:
    agg, clk = new_aggregate()
    agg.handle(CreateSession(clientCommandId="c", workoutRef="w1"))
    with pytest.raises(InvalidSessionTransitionError):
        agg.handle(StartSession(clientCommandId="s", sessionId=agg.sessionId))


def test_invalid_arm_after_start() -> None:
    agg, clk = started()
    with pytest.raises(InvalidSessionTransitionError):
        agg.handle(ArmSession(clientCommandId="arm2", sessionId=agg.sessionId))
