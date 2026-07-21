"""Typed persistence errors (Commit 7).

Raw filesystem, JSON, Unicode, and Pydantic errors never escape the public API; the
original exception is preserved via ``__cause__``.
"""

from __future__ import annotations


class PersistenceError(Exception):
    """Base class for all persistence errors."""


class EventLogError(PersistenceError):
    """Base class for event-journal errors."""


class EventLogCodecError(EventLogError):
    """The line could not be decoded/encoded (UTF-8, JSON parse, NaN/Infinity, blank)."""


class UnsupportedEventBatchVersionError(EventLogCodecError):
    """The record declares a recordVersion this codec cannot read."""


class InvalidEventBatchRecordError(EventLogCodecError):
    """The JSON parsed but is not a valid EventBatchRecord."""


class EventLogSequenceError(EventLogError):
    """The incoming batch's first seq is not last persisted seq + 1."""


class EventLogTimestampError(EventLogError):
    """The incoming batch's first event timestamp precedes the last persisted timestamp."""


class EventLogSessionMismatchError(EventLogError):
    """The incoming batch belongs to a different session than this journal."""


class EventLogDuplicateEventIdError(EventLogError):
    """An incoming eventId was already persisted."""


class EventLogConflictError(EventLogError):
    """Same seq/clientCommandId/eventId with different content, or a partial seq overlap."""


class EventLogWriteError(EventLogError):
    """The OS write failed; the final line may be partial — run recover_and_read()."""


class EventLogSyncError(EventLogError):
    """An fsync (file or parent directory) request failed."""


class EventLogDurabilityUncertainError(EventLogSyncError):
    """The full line was written but fsync failed: durability is unknown.

    The complete line is recognised on retry — resending the exact same batch will not
    write a duplicate; it re-fsyncs and returns ``ALREADY_PRESENT``.
    """


class CorruptEventLogError(EventLogError):
    """A record before the final line is invalid — never skipped, never auto-repaired."""


class TailRepairError(EventLogError):
    """The final line is incomplete; reading without repair refuses to drop bytes.

    Call ``recover_and_read()`` to truncate the partial tail explicitly.
    """
