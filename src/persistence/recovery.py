"""Explicit SessionRecovered orchestration (Commit 7, §18).

Reading a journal NEVER produces a ``SessionRecovered`` event automatically, and nothing
here appends to the historical source log. This helper only *builds* the typed event with
an injected Clock and EventIdGenerator; whether and where it is persisted is an explicit
caller decision.
"""

from __future__ import annotations

from contracts.enums import EventType
from contracts.events import Clock, EventEnvelope, EventIdGenerator, SessionRecoveredPayload


def build_session_recovered_event(
    *,
    session_id: str,
    client_command_id: str,
    last_recovered_seq: int,
    recovered_event_count: int,
    recovery_reason: str,
    clock: Clock,
    id_gen: EventIdGenerator,
    tail_truncated: bool = False,
    truncated_byte_count: int = 0,
    producer: str = "recovery",
) -> EventEnvelope:
    """Build a ``SessionRecovered`` marker event continuing the session sequence.

    ``seq`` is ``last_recovered_seq + 1`` so the marker extends the recovered stream
    contiguously. The event does not change the lifecycle state on replay; it only
    increments ``recoveryCount``.
    """
    return EventEnvelope(
        eventId=id_gen.next_id(),
        seq=last_recovered_seq + 1,
        sessionId=session_id,
        type=EventType.SessionRecovered,
        tsMs=clock.now_ms(),
        producer=producer,
        clientCommandId=client_command_id,
        payload=SessionRecoveredPayload(
            sessionId=session_id,
            recoveredEventCount=recovered_event_count,
            lastRecoveredSeq=last_recovered_seq,
            tailTruncated=tail_truncated,
            truncatedByteCount=truncated_byte_count,
            recoveryReason=recovery_reason,
        ),
    )
