"""Domain errors for the ghost primitive. Pure exception types only."""

from __future__ import annotations


class GhostError(Exception):
    """Base class for all ghost domain errors."""


class InvalidGhostTransitionError(GhostError):
    """A ghost state transition is not allowed from the current state."""


class InvalidAlignmentDistanceError(GhostError):
    """A StopPause alignment distance is non-finite, out of range, or otherwise invalid."""


class InvalidWallReconciliationError(GhostError):
    """Wall reconciliation was attempted with no pending alignment, at the wrong wall,
    or on a non-wall boundary."""
