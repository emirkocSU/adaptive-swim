"""Explicit domain exceptions for the pace-math engine.

Messages include the offending input values but are not UI copy. Only genuine domain
violations raise; everything else returns a value.
"""

from __future__ import annotations


class PaceMathError(Exception):
    """Base class for all pace-math domain errors."""


class InvalidPaceError(PaceMathError):
    pass


class InvalidDistanceError(PaceMathError):
    pass


class InvalidDurationError(PaceMathError):
    pass


class DistanceOutsideTimelineError(PaceMathError):
    pass


class TimeOutsideTimelineError(PaceMathError):
    pass


class InvalidPaceCurveError(PaceMathError):
    pass


class UnsupportedPaceModeError(PaceMathError):
    pass
