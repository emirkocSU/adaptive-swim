"""Session domain errors. No raw ValueError/KeyError/AssertionError escapes the aggregate."""

from __future__ import annotations


class SessionError(Exception):
    """Base class for all session domain errors."""


class SessionNotCreatedError(SessionError):
    pass


class InvalidSessionTransitionError(SessionError):
    pass


class SessionWorkoutValidationError(SessionError):
    pass


class DuplicateCommandError(SessionError):
    pass


class CommandIdConflictError(SessionError):
    pass


class SplitNotFoundError(SessionError):
    pass


class DuplicateSplitError(SessionError):
    pass


class SplitVerificationConflictError(SessionError):
    pass


class StopPauseAlreadyOpenError(SessionError):
    pass


class StopPauseNotOpenError(SessionError):
    pass


class StopPauseIntervalMismatchError(SessionError):
    pass


class PendingReconciliationError(SessionError):
    pass


class PacingResetAlreadyPendingError(SessionError):
    pass


class NoPendingPacingResetError(SessionError):
    pass


class SessionIdMismatchError(SessionError):
    pass


class WorkoutNotCompletedError(SessionError):
    pass


class InvalidSplitBoundaryError(SessionError):
    pass


class InvalidEventTimeError(SessionError):
    pass
