"""Lifecycle transition table + validation (pure)."""

from __future__ import annotations

from swimcore.session.errors import InvalidSessionTransitionError
from swimcore.session.state import TERMINAL_STATES, SessionState

#: command name -> (allowed source states, destination state)
LIFECYCLE_TRANSITIONS: dict[str, tuple[frozenset[SessionState], SessionState]] = {
    "ArmSession": (frozenset({SessionState.CREATED}), SessionState.ARMED),
    "StartSession": (frozenset({SessionState.ARMED}), SessionState.RUNNING),
    "PauseSession": (frozenset({SessionState.RUNNING}), SessionState.PAUSED),
    "ResumeSession": (frozenset({SessionState.PAUSED}), SessionState.RUNNING),
    "CompleteSession": (frozenset({SessionState.RUNNING}), SessionState.COMPLETED),
    "AbortSession": (
        frozenset(
            {
                SessionState.CREATED,
                SessionState.ARMED,
                SessionState.RUNNING,
                SessionState.PAUSED,
            }
        ),
        SessionState.ABORTED,
    ),
}


def next_state(command_type: str, current: SessionState) -> SessionState:
    entry = LIFECYCLE_TRANSITIONS.get(command_type)
    if entry is None:
        raise InvalidSessionTransitionError(f"{command_type} is not a lifecycle transition")
    allowed, dest = entry
    if current in TERMINAL_STATES:
        raise InvalidSessionTransitionError(
            f"{command_type} rejected: session is terminal ({current})"
        )
    if current not in allowed:
        raise InvalidSessionTransitionError(
            f"{command_type} invalid from {current}; allowed from {sorted(allowed)}"
        )
    return dest
