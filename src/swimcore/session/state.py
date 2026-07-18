"""Authoritative session lifecycle state. StopPause is NOT a lifecycle state."""

from __future__ import annotations

from enum import StrEnum


class SessionState(StrEnum):
    CREATED = "CREATED"
    ARMED = "ARMED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


TERMINAL_STATES: frozenset[SessionState] = frozenset({SessionState.COMPLETED, SessionState.ABORTED})
