"""Event-log persistence contract (Commit 7).

A single ``SessionAggregate.handle(command)`` call may produce several events (e.g.
``CreateSession`` → ``WorkoutValidated`` + ``SessionCreated``). If those events were
persisted as separate JSONL lines, a crash could leave only the first line durable and a
*half command* would replay. Therefore:

    all events of one command  ==  one ``EventBatchRecord``  ==  one canonical JSONL line

This module is pure (no I/O, no JSON encoding — the canonical byte codec lives in
``persistence.codec``). The generated schema ``event-batch-record-1.0.json`` must never be
edited by hand (``python -m swimtools.gen_schemas``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import model_validator

from contracts._base import NonEmptyStr, PosInt, SeqInt, StrictModel
from contracts.events import EventEnvelope
from contracts.version import SUPPORTED_EVENT_ENVELOPE_SCHEMA_VERSIONS


class EventBatchRecord(StrictModel):
    """All events produced by exactly one command, persisted as one JSONL line."""

    recordType: Literal["EVENT_BATCH"] = "EVENT_BATCH"
    recordVersion: Literal["1.0"] = "1.0"
    sessionId: NonEmptyStr
    clientCommandId: NonEmptyStr
    firstSeq: SeqInt
    lastSeq: SeqInt
    eventCount: PosInt
    events: tuple[EventEnvelope, ...]

    @model_validator(mode="after")
    def _validate_batch(self) -> EventBatchRecord:
        events = self.events
        if len(events) == 0:
            raise ValueError("an EventBatchRecord must contain at least one event")
        if self.eventCount != len(events):
            raise ValueError(f"eventCount {self.eventCount} != len(events) {len(events)}")
        if self.firstSeq != events[0].seq:
            raise ValueError(f"firstSeq {self.firstSeq} != first event seq {events[0].seq}")
        if self.lastSeq != events[-1].seq:
            raise ValueError(f"lastSeq {self.lastSeq} != last event seq {events[-1].seq}")
        seen_ids: set[str] = set()
        prev_seq: int | None = None
        prev_ts: int | None = None
        for event in events:
            if prev_seq is not None and event.seq != prev_seq + 1:
                raise ValueError(
                    f"event seq values must be contiguous: {prev_seq} then {event.seq}"
                )
            prev_seq = event.seq
            if event.sessionId != self.sessionId:
                raise ValueError(
                    f"event sessionId {event.sessionId!r} != batch sessionId {self.sessionId!r}"
                )
            if event.clientCommandId != self.clientCommandId:
                raise ValueError(
                    f"event clientCommandId {event.clientCommandId!r} != batch "
                    f"clientCommandId {self.clientCommandId!r}"
                )
            if prev_ts is not None and event.tsMs < prev_ts:
                raise ValueError(
                    f"event timestamps must be non-decreasing: {prev_ts} then {event.tsMs}"
                )
            prev_ts = event.tsMs
            if event.eventId in seen_ids:
                raise ValueError(f"duplicate eventId {event.eventId!r} inside the batch")
            seen_ids.add(event.eventId)
            if event.schemaVersion not in SUPPORTED_EVENT_ENVELOPE_SCHEMA_VERSIONS:
                raise ValueError(
                    f"unsupported event schemaVersion {event.schemaVersion!r} "
                    f"(supported: {sorted(SUPPORTED_EVENT_ENVELOPE_SCHEMA_VERSIONS)})"
                )
        return self

    @classmethod
    def from_events(cls, events: Sequence[EventEnvelope]) -> EventBatchRecord:
        """Build the batch record for one command's events.

        Deterministic and non-mutating: the same input event sequence always produces the
        same record, and the input envelopes are neither copied-and-changed nor mutated.
        All batch rules are enforced by the model validator above.
        """
        if len(events) == 0:
            raise ValueError("an EventBatchRecord must contain at least one event")
        first = events[0]
        if first.sessionId is None:
            raise ValueError("batch events must carry a sessionId")
        if first.clientCommandId is None:
            raise ValueError("batch events must carry a clientCommandId")
        return cls(
            sessionId=first.sessionId,
            clientCommandId=first.clientCommandId,
            firstSeq=first.seq,
            lastSeq=events[-1].seq,
            eventCount=len(events),
            events=tuple(events),
        )
