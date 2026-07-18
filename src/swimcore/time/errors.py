"""Domain errors for deterministic clock primitives (SimClock, ActiveClock).

Pure exception types only: no I/O, no framework, no side effects.
"""

from __future__ import annotations


class ClockError(Exception):
    """Base class for all clock domain errors."""


class InvalidClockTimeError(ClockError):
    """A time value is non-finite, negative, or moves backward past the last observed time."""


class ClockNotStartedError(ClockError):
    """An operation requiring a started clock was attempted before ``start``."""


class ClockAlreadyStartedError(ClockError):
    """``start`` was called on an already-started clock."""


class ClockAlreadyFrozenError(ClockError):
    """A StopPause freeze was requested while one is already open."""


class ClockNotFrozenError(ClockError):
    """``resume`` was called with no open StopPause."""


class InvalidStopIntervalError(ClockError):
    """A StopPause interval is internally inconsistent (ordering / overlap / bounds)."""
