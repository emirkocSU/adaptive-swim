"""Typed replay errors. No raw ValueError/KeyError escapes the reducer."""

from __future__ import annotations


class ReplayError(Exception):
    """Base class for all historical-replay errors."""


class EmptyReplayError(ReplayError):
    """The event stream is empty; there is nothing to replay."""


class ReplaySequenceError(ReplayError):
    """seq does not start at 1, is not contiguous, or repeats."""


class ReplayTimestampError(ReplayError):
    """Event timestamps decreased along the stream."""


class ReplaySessionMismatchError(ReplayError):
    """Events carry a different/missing sessionId, or the expected id does not match."""


class ReplayDuplicateEventIdError(ReplayError):
    """The same eventId appears more than once in the stream."""


class ReplayTransitionError(ReplayError):
    """A lifecycle event is invalid for the current historical state."""


class ReplaySplitError(ReplayError):
    """Split recording/verification is inconsistent (order, identity, conflicts)."""


class ReplayStopPauseError(ReplayError):
    """StopPause intervals are inconsistent (double-open, mismatch, overlap, corruption)."""


class ReplayDurationError(ReplayError):
    """The event stream implies a negative or contradictory duration."""


class ReplayCommandBatchError(ReplayError):
    """clientCommandId batches are not contiguous or a command id reappears later."""


class UnsupportedReplaySchemaError(ReplayError):
    """An event carries a schemaVersion this replay implementation cannot read."""
