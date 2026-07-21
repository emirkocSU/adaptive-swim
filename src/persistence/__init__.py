"""Adaptive Swim persistence (Commit 7): append-only JSONL event journal + recovery.

Layer rule: ``persistence`` may import ``contracts`` and ``swimcore.replay``; ``swimcore``
never imports ``persistence``. No SQLite/DB/ORM, no network, no web framework in Phase 1
(SQLite WAL projection is deferred to Phase 2, ADR-003/ADR-037).
"""

from persistence.codec import decode_batch, encode_batch
from persistence.errors import (
    CorruptEventLogError,
    EventLogCodecError,
    EventLogConflictError,
    EventLogDuplicateEventIdError,
    EventLogDurabilityUncertainError,
    EventLogError,
    EventLogSequenceError,
    EventLogSessionMismatchError,
    EventLogSyncError,
    EventLogTimestampError,
    EventLogWriteError,
    InvalidEventBatchRecordError,
    PersistenceError,
    TailRepairError,
    UnsupportedEventBatchVersionError,
)
from persistence.jsonl_event_log import JsonlSessionEventLog
from persistence.recovery import build_session_recovered_event
from persistence.types import (
    AppendBatchResult,
    AppendStatus,
    EventLogReadResult,
    LogTailTruncated,
    MissingFinalNewlineRepaired,
    ReadNotice,
)

__all__ = [
    "AppendBatchResult",
    "AppendStatus",
    "CorruptEventLogError",
    "EventLogCodecError",
    "EventLogConflictError",
    "EventLogDuplicateEventIdError",
    "EventLogDurabilityUncertainError",
    "EventLogError",
    "EventLogReadResult",
    "EventLogSequenceError",
    "EventLogSessionMismatchError",
    "EventLogSyncError",
    "EventLogTimestampError",
    "EventLogWriteError",
    "InvalidEventBatchRecordError",
    "JsonlSessionEventLog",
    "LogTailTruncated",
    "MissingFinalNewlineRepaired",
    "PersistenceError",
    "ReadNotice",
    "TailRepairError",
    "UnsupportedEventBatchVersionError",
    "build_session_recovered_event",
    "decode_batch",
    "encode_batch",
]
