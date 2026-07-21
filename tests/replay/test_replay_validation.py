"""Replay stream validation tests (Commit 7 §17, §20)."""

from __future__ import annotations

import pytest

from contracts.enums import EventType
from contracts.events import SessionArmedPayload
from swimcore.replay import (
    ReplayCommandBatchError,
    ReplayDuplicateEventIdError,
    ReplaySequenceError,
    ReplaySessionMismatchError,
    ReplayTimestampError,
    UnsupportedReplaySchemaError,
    replay_session,
    validate_event_stream,
)
from tests.replay._stream_helpers import SID, StreamBuilder

pytestmark = pytest.mark.replay


def armed_payload() -> SessionArmedPayload:
    return SessionArmedPayload(sessionId=SID)


def test_seq_must_start_at_one() -> None:
    b = StreamBuilder()
    b.add(EventType.SessionArmed, armed_payload(), 0, seq=2)
    with pytest.raises(ReplaySequenceError, match="from 1"):
        validate_event_stream(b.events)


def test_seq_gap_rejected() -> None:
    b = StreamBuilder().created(0)
    b.add(EventType.SessionArmed, armed_payload(), 0, seq=5)
    with pytest.raises(ReplaySequenceError):
        replay_session(b.events)


def test_duplicate_seq_rejected() -> None:
    b = StreamBuilder().created(0)
    b.add(EventType.SessionArmed, armed_payload(), 0, seq=2, event_id="evt-x")
    with pytest.raises(ReplaySequenceError, match="duplicate seq"):
        validate_event_stream(b.events)


def test_duplicate_event_id_rejected() -> None:
    b = StreamBuilder().created(0)
    b.add(EventType.SessionArmed, armed_payload(), 0, event_id="evt-1")
    with pytest.raises(ReplayDuplicateEventIdError):
        validate_event_stream(b.events)


def test_mixed_session_rejected() -> None:
    b = StreamBuilder().created(0)
    b.add(EventType.SessionArmed, armed_payload(), 0, session_id="session-other")
    with pytest.raises(ReplaySessionMismatchError):
        validate_event_stream(b.events)


def test_expected_session_id_mismatch_rejected() -> None:
    b = StreamBuilder().created(0)
    with pytest.raises(ReplaySessionMismatchError, match="expected"):
        replay_session(b.events, expected_session_id="session-else")
    # and the matching id passes
    assert validate_event_stream(b.events, expected_session_id=SID) == SID


def test_missing_session_id_rejected() -> None:
    b = StreamBuilder()
    b.add(EventType.SessionArmed, armed_payload(), 0, session_id=None)
    # builder sets session on all; force None via direct construction
    events = [b.events[0].model_copy(update={"sessionId": None})]
    with pytest.raises(ReplaySessionMismatchError, match="no sessionId"):
        validate_event_stream(events)


def test_timestamp_regression_rejected() -> None:
    b = StreamBuilder().created(5_000)
    b.add(EventType.SessionArmed, armed_payload(), 1_000)
    with pytest.raises(ReplayTimestampError):
        validate_event_stream(b.events)


def test_unsupported_schema_version_rejected() -> None:
    b = StreamBuilder().created(0)
    b.add(EventType.SessionArmed, armed_payload(), 0, schema="9.9")
    with pytest.raises(UnsupportedReplaySchemaError):
        validate_event_stream(b.events)


def test_missing_client_command_id_rejected() -> None:
    b = StreamBuilder().created(0)
    events = [*b.events[:-1], b.events[-1].model_copy(update={"clientCommandId": None})]
    with pytest.raises(ReplayCommandBatchError, match="no clientCommandId"):
        validate_event_stream(events)


def test_command_id_must_be_contiguous() -> None:
    """§17: the same clientCommandId may not reappear in a later stream section."""
    b = StreamBuilder()
    b.add(EventType.SessionArmed, armed_payload(), 0, cid="cmd-A")
    b.add(EventType.SessionArmed, armed_payload(), 0, cid="cmd-B")
    b.add(EventType.SessionArmed, armed_payload(), 0, cid="cmd-A")  # reappears later
    with pytest.raises(ReplayCommandBatchError, match="reappears"):
        validate_event_stream(b.events)


def test_contiguous_multi_event_command_accepted() -> None:
    b = StreamBuilder().created(0)  # one cid over two events (WorkoutValidated+Created)
    assert validate_event_stream(b.events) == SID
