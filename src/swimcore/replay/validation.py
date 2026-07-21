"""Structural validation of an event stream before folding (pure, no I/O).

Fold-dependent rules (lifecycle transitions, split ordering, StopPause pairing) are
enforced inside the reducer with their own typed errors; this module checks everything
that can be decided from the envelopes alone.
"""

from __future__ import annotations

from collections.abc import Sequence

from contracts.events import EventEnvelope
from contracts.version import SUPPORTED_EVENT_ENVELOPE_SCHEMA_VERSIONS
from swimcore.replay.errors import (
    EmptyReplayError,
    ReplayCommandBatchError,
    ReplayDuplicateEventIdError,
    ReplaySequenceError,
    ReplaySessionMismatchError,
    ReplayTimestampError,
    UnsupportedReplaySchemaError,
)


def validate_event_stream(
    events: Sequence[EventEnvelope],
    *,
    expected_session_id: str | None = None,
) -> str:
    """Validate the stream structurally; return the (single) session id.

    Rules: non-empty; seq starts at 1 and is strictly contiguous (duplicates rejected);
    eventIds unique; all events carry the same non-null sessionId (matching
    ``expected_session_id`` when given); timestamps never decrease; every schemaVersion is
    supported; events of one clientCommandId are contiguous and a command id never
    reappears in a later section of the stream.
    """
    if len(events) == 0:
        raise EmptyReplayError("cannot replay an empty event stream")

    session_id = events[0].sessionId
    if session_id is None:
        raise ReplaySessionMismatchError("first event carries no sessionId")
    if expected_session_id is not None and session_id != expected_session_id:
        raise ReplaySessionMismatchError(
            f"stream sessionId {session_id!r} != expected {expected_session_id!r}"
        )

    seen_event_ids: set[str] = set()
    finished_command_ids: set[str] = set()
    current_command_id: str | None = None
    prev_seq = 0
    prev_ts: int | None = None

    for event in events:
        if event.seq != prev_seq + 1:
            if event.seq == prev_seq:
                raise ReplaySequenceError(f"duplicate seq {event.seq}")
            raise ReplaySequenceError(
                f"seq must be contiguous from 1: expected {prev_seq + 1}, got {event.seq}"
            )
        prev_seq = event.seq

        if event.eventId in seen_event_ids:
            raise ReplayDuplicateEventIdError(f"duplicate eventId {event.eventId!r}")
        seen_event_ids.add(event.eventId)

        if event.sessionId != session_id:
            raise ReplaySessionMismatchError(
                f"event seq {event.seq} sessionId {event.sessionId!r} != {session_id!r}"
            )

        if prev_ts is not None and event.tsMs < prev_ts:
            raise ReplayTimestampError(
                f"event seq {event.seq} timestamp {event.tsMs} < previous {prev_ts}"
            )
        prev_ts = event.tsMs

        if event.schemaVersion not in SUPPORTED_EVENT_ENVELOPE_SCHEMA_VERSIONS:
            raise UnsupportedReplaySchemaError(
                f"event seq {event.seq} schemaVersion {event.schemaVersion!r} unsupported "
                f"(supported: {sorted(SUPPORTED_EVENT_ENVELOPE_SCHEMA_VERSIONS)})"
            )

        cid = event.clientCommandId
        if cid is None:
            raise ReplayCommandBatchError(f"event seq {event.seq} carries no clientCommandId")
        if cid != current_command_id:
            if current_command_id is not None:
                finished_command_ids.add(current_command_id)
            if cid in finished_command_ids:
                raise ReplayCommandBatchError(
                    f"clientCommandId {cid!r} reappears in a later section of the stream"
                )
            current_command_id = cid

    return session_id
