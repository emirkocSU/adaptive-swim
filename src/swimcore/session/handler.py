"""Pure helpers for the session aggregate: deterministic command fingerprint + event factory.

No I/O, no system time, no randomness — the clock and id generator are injected.
"""

from __future__ import annotations

from contracts.commands import Command
from contracts.enums import EventType
from contracts.events import PAYLOAD_FOR_EVENT, EventEnvelope, EventIdGenerator
from contracts.events import Clock as ClockProto
from swimcore.session.errors import InvalidEventTimeError


def command_fingerprint(command: Command) -> str:
    """Deterministic content hash of a command (excluding nothing; stable JSON)."""
    return command.model_dump_json()


class EventFactory:
    """Builds typed ``EventEnvelope``s with a monotonic session-local sequence."""

    def __init__(self, id_gen: EventIdGenerator, producer: str = "session") -> None:
        self._id_gen = id_gen
        self._producer = producer
        self._seq = 0
        self._last_ts_ms = 0

    @property
    def last_ts_ms(self) -> int:
        return self._last_ts_ms

    def build(
        self,
        event_type: EventType,
        payload: object,
        occurred_at_ms: int,
        session_id: str | None,
        client_command_id: str | None,
    ) -> EventEnvelope:
        return self.build_batch(
            [(event_type, payload, occurred_at_ms)], session_id, client_command_id
        )[0]

    def build_batch(
        self,
        specs: list[tuple[EventType, object, int]],
        session_id: str | None,
        client_command_id: str | None,
    ) -> list[EventEnvelope]:
        """Atomically build a batch of events.

        All payloads/types/timestamps are validated first; the factory's ``seq`` and
        ``last_ts`` are advanced only if the whole batch succeeds. Event timestamps are
        forward-only (``occurredAtMs`` may equal but never precede the last event time);
        historical timestamps are rejected rather than silently clamped. A single command
        may emit several events sharing one timestamp.
        """
        # validate against a local copy first (atomic)
        local_seq = self._seq
        local_ts = self._last_ts_ms
        prepared: list[tuple[EventType, object, int, int]] = []
        for event_type, payload, occurred_at_ms in specs:
            if occurred_at_ms < local_ts:
                raise InvalidEventTimeError(
                    f"event time {occurred_at_ms} precedes last event time {local_ts}"
                )
            expected = PAYLOAD_FOR_EVENT[event_type]
            if not isinstance(payload, expected):
                raise TypeError(f"payload {type(payload).__name__} != {expected.__name__}")
            local_seq += 1
            local_ts = occurred_at_ms
            prepared.append((event_type, payload, occurred_at_ms, local_seq))

        events: list[EventEnvelope] = []
        for event_type, payload, occurred_at_ms, seq in prepared:
            events.append(
                EventEnvelope(
                    eventId=self._id_gen.next_id(),
                    seq=seq,
                    sessionId=session_id,
                    type=event_type,
                    tsMs=occurred_at_ms,
                    producer=self._producer,
                    clientCommandId=client_command_id,
                    payload=payload,  # type: ignore[arg-type]
                )
            )
        # commit only after every event was constructed successfully
        self._seq = local_seq
        self._last_ts_ms = local_ts
        return events


class SequenceIdGenerator:
    """Deterministic event-id generator for tests/simulation (no randomness)."""

    def __init__(self, prefix: str = "evt") -> None:
        self._prefix = prefix
        self._n = 0

    def next_id(self) -> str:
        self._n += 1
        return f"{self._prefix}-{self._n}"


class FixedClock:
    """Minimal injected clock (satisfies contracts.events.Clock)."""

    def __init__(self, now_ms: int = 0) -> None:
        self._now = now_ms

    def now_ms(self) -> int:
        return self._now

    def set(self, now_ms: int) -> None:
        self._now = now_ms


__all__ = [
    "ClockProto",
    "EventFactory",
    "FixedClock",
    "SequenceIdGenerator",
    "command_fingerprint",
]
