"""Deterministic session orchestration layer (Commit 6).

Pure in-memory domain flow: state machine, typed command handling, idempotency, StopPause
orchestration, coach pacing reset, split recording/verification, and safety-gated pace
changes. No persistence/replay/simulator/ML/UI/device — those are later commits.
"""

from swimcore.session.aggregate import SessionAggregate
from swimcore.session.errors import (
    CommandIdConflictError,
    DuplicateCommandError,
    DuplicateSplitError,
    InvalidSessionTransitionError,
    NoPendingPacingResetError,
    PacingResetAlreadyPendingError,
    PendingReconciliationError,
    SessionError,
    SessionNotCreatedError,
    SessionWorkoutValidationError,
    SplitNotFoundError,
    SplitVerificationConflictError,
    StopPauseAlreadyOpenError,
    StopPauseIntervalMismatchError,
    StopPauseNotOpenError,
)
from swimcore.session.handler import (
    EventFactory,
    FixedClock,
    SequenceIdGenerator,
    command_fingerprint,
)
from swimcore.session.state import TERMINAL_STATES, SessionState
from swimcore.session.transitions import LIFECYCLE_TRANSITIONS, next_state

__all__ = [
    "LIFECYCLE_TRANSITIONS",
    "TERMINAL_STATES",
    "CommandIdConflictError",
    "DuplicateCommandError",
    "DuplicateSplitError",
    "EventFactory",
    "FixedClock",
    "InvalidSessionTransitionError",
    "NoPendingPacingResetError",
    "PacingResetAlreadyPendingError",
    "PendingReconciliationError",
    "SequenceIdGenerator",
    "SessionAggregate",
    "SessionError",
    "SessionNotCreatedError",
    "SessionState",
    "SessionWorkoutValidationError",
    "SplitNotFoundError",
    "SplitVerificationConflictError",
    "StopPauseAlreadyOpenError",
    "StopPauseIntervalMismatchError",
    "StopPauseNotOpenError",
    "command_fingerprint",
    "next_state",
]
