"""EventBatchRecord contract tests (Commit 7 §6, §20)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.enums import EventType
from contracts.event_log import EventBatchRecord
from contracts.events import EventEnvelope, SessionArmedPayload

pytestmark = pytest.mark.replay

SID = "session-x"


def env(
    seq: int,
    *,
    ts: int = 1000,
    event_id: str | None = None,
    session: str = SID,
    cid: str = "cmd-1",
    schema: str = "1.0",
) -> EventEnvelope:
    return EventEnvelope(
        eventId=event_id or f"evt-{seq}",
        seq=seq,
        sessionId=session,
        type=EventType.SessionArmed,
        tsMs=ts,
        schemaVersion=schema,
        producer="test",
        clientCommandId=cid,
        payload=SessionArmedPayload(sessionId=session),
    )


def test_from_events_builds_valid_record() -> None:
    events = [env(1), env(2, ts=1500)]
    record = EventBatchRecord.from_events(events)
    assert record.recordType == "EVENT_BATCH"
    assert record.recordVersion == "1.0"
    assert record.sessionId == SID
    assert record.clientCommandId == "cmd-1"
    assert (record.firstSeq, record.lastSeq, record.eventCount) == (1, 2, 2)


def test_empty_batch_rejected() -> None:
    with pytest.raises(ValueError, match="at least one event"):
        EventBatchRecord.from_events([])


def test_event_count_mismatch_rejected() -> None:
    events = (env(1), env(2))
    with pytest.raises(ValidationError, match="eventCount"):
        EventBatchRecord(
            sessionId=SID,
            clientCommandId="cmd-1",
            firstSeq=1,
            lastSeq=2,
            eventCount=3,
            events=events,
        )


def test_first_last_seq_must_match_events() -> None:
    events = (env(1), env(2))
    with pytest.raises(ValidationError, match="firstSeq"):
        EventBatchRecord(
            sessionId=SID,
            clientCommandId="cmd-1",
            firstSeq=2,
            lastSeq=2,
            eventCount=2,
            events=events,
        )
    with pytest.raises(ValidationError, match="lastSeq"):
        EventBatchRecord(
            sessionId=SID,
            clientCommandId="cmd-1",
            firstSeq=1,
            lastSeq=3,
            eventCount=2,
            events=events,
        )


def test_seq_discontinuity_rejected() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        EventBatchRecord.from_events([env(1), env(3)])


def test_mixed_session_rejected() -> None:
    with pytest.raises(ValidationError, match="sessionId"):
        EventBatchRecord.from_events([env(1), env(2, session="session-other")])


def test_mixed_command_id_rejected() -> None:
    with pytest.raises(ValidationError, match="clientCommandId"):
        EventBatchRecord.from_events([env(1), env(2, cid="cmd-2")])


def test_duplicate_event_id_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate eventId"):
        EventBatchRecord.from_events([env(1, event_id="same"), env(2, event_id="same")])


def test_decreasing_timestamp_rejected() -> None:
    with pytest.raises(ValidationError, match="non-decreasing"):
        EventBatchRecord.from_events([env(1, ts=2000), env(2, ts=1000)])


def test_unsupported_event_schema_version_rejected() -> None:
    with pytest.raises(ValidationError, match="schemaVersion"):
        EventBatchRecord.from_events([env(1, schema="9.9")])


def test_missing_session_or_command_id_rejected() -> None:
    bare = EventEnvelope(
        eventId="evt-1",
        seq=1,
        sessionId=None,
        type=EventType.SessionArmed,
        tsMs=0,
        producer="test",
        clientCommandId="cmd-1",
        payload=SessionArmedPayload(sessionId=SID),
    )
    with pytest.raises(ValueError, match="sessionId"):
        EventBatchRecord.from_events([bare])
    no_cid = EventEnvelope(
        eventId="evt-1",
        seq=1,
        sessionId=SID,
        type=EventType.SessionArmed,
        tsMs=0,
        producer="test",
        clientCommandId=None,
        payload=SessionArmedPayload(sessionId=SID),
    )
    with pytest.raises(ValueError, match="clientCommandId"):
        EventBatchRecord.from_events([no_cid])


def test_extra_fields_rejected() -> None:
    record = EventBatchRecord.from_events([env(1)])
    data = record.model_dump(mode="json")
    data["surprise"] = 1
    with pytest.raises(ValidationError):
        EventBatchRecord.model_validate(data)


def test_factory_is_deterministic_and_does_not_mutate() -> None:
    events = [env(1), env(2, ts=1500)]
    before = [e.model_dump(mode="json") for e in events]
    r1 = EventBatchRecord.from_events(events)
    r2 = EventBatchRecord.from_events(events)
    assert r1 == r2
    assert r1.model_dump(mode="json") == r2.model_dump(mode="json")
    assert [e.model_dump(mode="json") for e in events] == before
    assert list(r1.events) == events  # same envelopes, not copies-with-changes
