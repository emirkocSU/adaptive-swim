"""Append-only JSONL session event journal (Commit 7, ADR-037).

One command's events = one :class:`EventBatchRecord` = one canonical JSONL line. The line
is prepared as a single bytes buffer, written with a partial-write/EINTR-safe loop, and
``os.fsync``'ed before the append reports success. There is no background writer thread and
no timer-based batching: durability is requested synchronously per command batch.

Durability honesty (ADR-037): ``fsync`` is a durability *request* to the filesystem and
storage stack. Surviving ``kill -9`` is not the same as surviving a power cut or hardware
failure; no absolute guarantee is claimed for the latter. A Commit-7 success result is
returned only after both the write and the fsync completed.

Tail semantics:
- final line valid **and** newline-terminated → normal;
- final record valid but missing its newline → accepted; repair only appends the newline
  (``MissingFinalNewlineRepaired``; not data loss);
- final line torn (undecodable) → only that incomplete tail is truncated in repair mode
  (``LogTailTruncated``); prior complete batches are never touched;
- an invalid line **before** the tail, an invalid newline-terminated final line, or a blank
  line → :class:`CorruptEventLogError`; corruption is never skipped and never auto-repaired.
"""

from __future__ import annotations

import errno
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from contracts.event_log import EventBatchRecord
from contracts.events import EventEnvelope
from persistence.codec import decode_batch, encode_batch
from persistence.errors import (
    CorruptEventLogError,
    EventLogCodecError,
    EventLogConflictError,
    EventLogDuplicateEventIdError,
    EventLogDurabilityUncertainError,
    EventLogSequenceError,
    EventLogSessionMismatchError,
    EventLogTimestampError,
    EventLogWriteError,
    InvalidEventBatchRecordError,
    TailRepairError,
    UnsupportedEventBatchVersionError,
)
from persistence.types import (
    AppendBatchResult,
    AppendStatus,
    EventLogReadResult,
    LogTailTruncated,
    MissingFinalNewlineRepaired,
    ReadNotice,
)

_NEWLINE = b"\n"


@dataclass(frozen=True, slots=True)
class _PersistedBatch:
    clientCommandId: str
    firstSeq: int
    lastSeq: int
    canonical: bytes


class JsonlSessionEventLog:
    """Append-only, fsync-per-batch JSONL journal for one session."""

    def __init__(self, path: Path, session_id: str) -> None:
        self._path = Path(path)
        self._session_id = session_id
        self._loaded = False
        self._dir_synced = False
        self._last_seq = 0
        self._last_ts = 0
        self._event_ids: set[str] = set()
        self._batches: list[_PersistedBatch] = []
        self._batch_by_cid: dict[str, int] = {}
        #: True when a full line is on disk but its fsync failed (durability uncertain).
        self._pending_fsync = False

    # ------------------------------------------------------------------ public API
    @property
    def path(self) -> Path:
        return self._path

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def last_seq(self) -> int:
        self._ensure_loaded(repair=False)
        return self._last_seq

    def append_batch(self, events: Sequence[EventEnvelope]) -> AppendBatchResult:
        """Persist one command's events as one canonical JSONL line, fsync'ed.

        Exact-duplicate retries are idempotent (``ALREADY_PRESENT``; the existing line is
        re-fsynced). Any same-seq/same-command/same-eventId difference in content, or a
        partial seq overlap, is a conflict.
        """
        self._ensure_loaded(repair=False)
        try:
            record = EventBatchRecord.from_events(events)
        except (ValueError, TypeError) as exc:
            raise InvalidEventBatchRecordError(f"invalid event batch: {exc}") from exc
        if record.sessionId != self._session_id:
            raise EventLogSessionMismatchError(
                f"batch sessionId {record.sessionId!r} != journal session {self._session_id!r}"
            )
        canonical = encode_batch(record)

        duplicate = self._match_existing(record, canonical)
        if duplicate is not None:
            self._fsync_existing()
            return AppendBatchResult(
                status=AppendStatus.ALREADY_PRESENT,
                firstSeq=record.firstSeq,
                lastSeq=record.lastSeq,
                eventCount=record.eventCount,
                fsynced=True,
                bytesWritten=0,
            )

        # fresh append — validate against the persisted history
        if record.firstSeq != self._last_seq + 1:
            raise EventLogSequenceError(
                f"batch firstSeq {record.firstSeq} != last persisted seq + 1 ({self._last_seq + 1})"
            )
        first_ts = record.events[0].tsMs
        if first_ts < self._last_ts:
            raise EventLogTimestampError(
                f"batch first timestamp {first_ts} precedes last persisted {self._last_ts}"
            )
        for event in record.events:
            if event.eventId in self._event_ids:
                raise EventLogDuplicateEventIdError(f"eventId {event.eventId!r} already persisted")

        created = not self._path.exists()
        self._write_line_and_fsync(canonical, record)
        if created or not self._dir_synced:
            self._sync_parent_dir()
        return AppendBatchResult(
            status=AppendStatus.APPENDED,
            firstSeq=record.firstSeq,
            lastSeq=record.lastSeq,
            eventCount=record.eventCount,
            fsynced=True,
            bytesWritten=len(canonical),
        )

    def read_all(self, *, repair_tail: bool = False) -> EventLogReadResult:
        """Read and validate the whole journal.

        With ``repair_tail=False`` the file is never modified: a torn final line raises
        :class:`TailRepairError` instead of silently dropping bytes. A valid final record
        that merely misses its newline is accepted in both modes (no data loss).
        """
        batches, notices, size = self._parse_file(repair=repair_tail)
        self._rebuild_index(batches)
        events = tuple(e for b in batches for e in b.events)
        return EventLogReadResult(
            batches=tuple(batches),
            events=events,
            notices=tuple(notices),
            fileSizeBytes=size,
        )

    def recover_and_read(self) -> EventLogReadResult:
        """Read with explicit repair: truncate a torn tail / terminate a valid tail.

        Idempotent — running it again on an already-recovered file changes nothing and
        produces no further notices.
        """
        return self.read_all(repair_tail=True)

    # ------------------------------------------------------------------ internals
    def _ensure_loaded(self, *, repair: bool) -> None:
        if self._loaded:
            return
        batches, _notices, _size = self._parse_file(repair=repair)
        self._rebuild_index(batches)

    def _rebuild_index(self, batches: Sequence[EventBatchRecord]) -> None:
        self._last_seq = 0
        self._last_ts = 0
        self._event_ids = set()
        self._batches = []
        self._batch_by_cid = {}
        for record in batches:
            self._register(record, encode_batch(record))
        self._loaded = True

    def _register(self, record: EventBatchRecord, canonical: bytes) -> None:
        index = len(self._batches)
        self._batches.append(
            _PersistedBatch(
                clientCommandId=record.clientCommandId,
                firstSeq=record.firstSeq,
                lastSeq=record.lastSeq,
                canonical=canonical,
            )
        )
        self._batch_by_cid[record.clientCommandId] = index
        self._last_seq = record.lastSeq
        self._last_ts = record.events[-1].tsMs
        for event in record.events:
            self._event_ids.add(event.eventId)

    def _match_existing(self, record: EventBatchRecord, canonical: bytes) -> int | None:
        """Return the index of an exact persisted duplicate, or raise on conflict."""
        existing_index = self._batch_by_cid.get(record.clientCommandId)
        if existing_index is not None:
            if self._batches[existing_index].canonical == canonical:
                return existing_index
            raise EventLogConflictError(
                f"clientCommandId {record.clientCommandId!r} was persisted with different content"
            )
        if record.firstSeq <= self._last_seq:
            # Overlaps persisted seq range without matching any persisted command exactly:
            # same seq with different content, or a partial overlap.
            raise EventLogConflictError(
                f"batch seq range [{record.firstSeq}, {record.lastSeq}] overlaps persisted "
                f"events up to seq {self._last_seq} with different content"
            )
        return None

    def _write_line_and_fsync(self, canonical: bytes, record: EventBatchRecord) -> None:
        try:
            fd = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        except OSError as exc:
            raise EventLogWriteError(f"cannot open journal {self._path}: {exc}") from exc
        try:
            self._write_all(fd, canonical)
            try:
                os.fsync(fd)
            except OSError as exc:
                # The full line IS on disk; only its durability is unknown. Register it so
                # an exact retry is recognised (no duplicate line) and can re-fsync.
                self._register(record, canonical)
                self._pending_fsync = True
                raise EventLogDurabilityUncertainError(
                    "the batch line was fully written but fsync failed; durability is "
                    "uncertain — retry the exact same batch to re-fsync"
                ) from exc
        finally:
            os.close(fd)
        self._register(record, canonical)
        self._pending_fsync = False

    @staticmethod
    def _write_all(fd: int, data: bytes) -> None:
        """Write every byte (os.write may write partially; EINTR is retried)."""
        view = memoryview(data)
        written = 0
        while written < len(data):
            try:
                written += os.write(fd, view[written:])
            except InterruptedError:
                continue
            except OSError as exc:
                if exc.errno == errno.EINTR:  # pragma: no cover - InterruptedError path above
                    continue
                raise EventLogWriteError(
                    f"write failed after {written}/{len(data)} bytes; the final line may be "
                    "partial — run recover_and_read() before appending again"
                ) from exc

    def _fsync_existing(self) -> None:
        """Re-fsync the journal file to reinforce durability of an already-present line."""
        try:
            fd = os.open(self._path, os.O_RDONLY)
        except OSError as exc:
            raise EventLogDurabilityUncertainError(
                f"cannot open journal for re-fsync: {exc}"
            ) from exc
        try:
            try:
                os.fsync(fd)
            except OSError as exc:
                raise EventLogDurabilityUncertainError(
                    "re-fsync of the existing line failed; durability is still uncertain"
                ) from exc
        finally:
            os.close(fd)
        self._pending_fsync = False

    def _sync_parent_dir(self) -> None:
        """Sync the parent directory entry after the journal file is first created."""
        parent = self._path.resolve().parent
        try:
            dir_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            return  # platform without directory open support; file fsync already done
        try:
            try:
                os.fsync(dir_fd)
            except OSError as exc:
                raise EventLogDurabilityUncertainError(
                    f"parent directory sync failed for {parent}: durability of the new "
                    "journal file entry is uncertain"
                ) from exc
        finally:
            os.close(dir_fd)
        self._dir_synced = True

    # ------------------------------------------------------------------ parsing / recovery
    def _parse_file(self, *, repair: bool) -> tuple[list[EventBatchRecord], list[ReadNotice], int]:
        if not self._path.exists():
            return [], [], 0
        data = self._path.read_bytes()
        original_size = len(data)
        notices: list[ReadNotice] = []
        if data == b"":
            return [], [], 0

        if data.endswith(_NEWLINE):
            complete = data[:-1].split(_NEWLINE)
            tail: bytes | None = None
        else:
            segments = data.split(_NEWLINE)
            complete = segments[:-1]
            tail = segments[-1]

        batches: list[EventBatchRecord] = []
        for i, segment in enumerate(complete):
            if segment.strip() == b"":
                raise CorruptEventLogError(
                    f"blank line at record {i} — an empty line is corruption, not padding"
                )
            try:
                batches.append(decode_batch(segment))
            except EventLogCodecError as exc:
                # A newline-terminated invalid line is corruption wherever it sits — the
                # middle is never skipped and a completed final line is not a torn tail.
                raise CorruptEventLogError(
                    f"invalid newline-terminated record at line {i}: {exc}"
                ) from exc

        if tail is not None:
            tail_record = self._parse_tail(tail, original_size, notices, repair=repair)
            if tail_record is not None:
                batches.append(tail_record)

        self._validate_cross_batches(batches)
        size = self._path.stat().st_size
        return batches, notices, size

    def _parse_tail(
        self,
        tail: bytes,
        original_size: int,
        notices: list[ReadNotice],
        *,
        repair: bool,
    ) -> EventBatchRecord | None:
        try:
            record = decode_batch(tail)
        except (UnsupportedEventBatchVersionError, InvalidEventBatchRecordError) as exc:
            # JSON parsed fully but the record itself is wrong — that is corruption, not a
            # torn write.
            raise CorruptEventLogError(f"invalid final record: {exc}") from exc
        except EventLogCodecError as exc:
            # Torn write: undecodable bytes after the last complete newline.
            if not repair:
                raise TailRepairError(
                    f"the final line is incomplete ({len(tail)} bytes after the last "
                    "newline); call recover_and_read() to truncate it explicitly"
                ) from exc
            truncate_offset = original_size - len(tail)
            self._truncate_to(truncate_offset)
            notices.append(
                LogTailTruncated(
                    originalSizeBytes=original_size,
                    recoveredSizeBytes=truncate_offset,
                    truncatedByteCount=len(tail),
                    truncateOffset=truncate_offset,
                )
            )
            return None
        # Valid record, only the newline is missing: accepted; repaired by appending "\n".
        if repair:
            self._append_final_newline()
            notices.append(MissingFinalNewlineRepaired(originalSizeBytes=original_size))
        return record

    def _truncate_to(self, offset: int) -> None:
        try:
            fd = os.open(self._path, os.O_RDWR)
        except OSError as exc:
            raise EventLogWriteError(f"cannot open journal for repair: {exc}") from exc
        try:
            os.ftruncate(fd, offset)
            os.fsync(fd)
        except OSError as exc:
            raise EventLogWriteError(f"tail truncation failed: {exc}") from exc
        finally:
            os.close(fd)

    def _append_final_newline(self) -> None:
        try:
            fd = os.open(self._path, os.O_WRONLY | os.O_APPEND)
        except OSError as exc:
            raise EventLogWriteError(f"cannot open journal for repair: {exc}") from exc
        try:
            self._write_all(fd, _NEWLINE)
            os.fsync(fd)
        except OSError as exc:
            raise EventLogWriteError(f"newline repair failed: {exc}") from exc
        finally:
            os.close(fd)

    def _validate_cross_batches(self, batches: Sequence[EventBatchRecord]) -> None:
        expected_seq = 1
        last_ts: int | None = None
        seen_event_ids: set[str] = set()
        seen_cids: set[str] = set()
        for record in batches:
            if record.sessionId != self._session_id:
                raise CorruptEventLogError(
                    f"journal contains sessionId {record.sessionId!r}; expected "
                    f"{self._session_id!r}"
                )
            if record.firstSeq != expected_seq:
                raise CorruptEventLogError(
                    f"journal seq gap: expected {expected_seq}, found batch starting at "
                    f"{record.firstSeq}"
                )
            expected_seq = record.lastSeq + 1
            if record.clientCommandId in seen_cids:
                raise CorruptEventLogError(
                    f"clientCommandId {record.clientCommandId!r} appears in two batches"
                )
            seen_cids.add(record.clientCommandId)
            for event in record.events:
                if last_ts is not None and event.tsMs < last_ts:
                    raise CorruptEventLogError(f"journal timestamp regression at seq {event.seq}")
                last_ts = event.tsMs
                if event.eventId in seen_event_ids:
                    raise CorruptEventLogError(f"duplicate eventId {event.eventId!r} in journal")
                seen_event_ids.add(event.eventId)
