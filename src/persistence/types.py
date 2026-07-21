"""Persistence result and recovery-notice types (Commit 7)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from contracts.event_log import EventBatchRecord
from contracts.events import EventEnvelope


class AppendStatus(StrEnum):
    APPENDED = "APPENDED"
    ALREADY_PRESENT = "ALREADY_PRESENT"


@dataclass(frozen=True, slots=True)
class AppendBatchResult:
    status: AppendStatus
    firstSeq: int
    lastSeq: int
    eventCount: int
    fsynced: bool
    bytesWritten: int


@dataclass(frozen=True, slots=True)
class LogTailTruncated:
    """The final incomplete line was removed; every prior complete batch is untouched."""

    originalSizeBytes: int
    recoveredSizeBytes: int
    truncatedByteCount: int
    truncateOffset: int


@dataclass(frozen=True, slots=True)
class MissingFinalNewlineRepaired:
    """The final record was valid but unterminated; only a newline was appended.

    This is a normalisation, not data loss — ``LogTailTruncated`` is never used for it.
    """

    originalSizeBytes: int


ReadNotice = LogTailTruncated | MissingFinalNewlineRepaired


@dataclass(frozen=True, slots=True)
class EventLogReadResult:
    batches: tuple[EventBatchRecord, ...]
    events: tuple[EventEnvelope, ...]
    notices: tuple[ReadNotice, ...]
    fileSizeBytes: int
