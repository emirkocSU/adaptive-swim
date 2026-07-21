"""Failure/durability semantics + SessionRecovered helper tests (Commit 7 §10, §12, §18)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from persistence.errors import (
    CorruptEventLogError,
    EventLogCodecError,
    EventLogDurabilityUncertainError,
    EventLogError,
    EventLogSyncError,
    EventLogWriteError,
    InvalidEventBatchRecordError,
    PersistenceError,
    TailRepairError,
    UnsupportedEventBatchVersionError,
)
from persistence.jsonl_event_log import JsonlSessionEventLog
from persistence.recovery import build_session_recovered_event
from persistence.types import AppendStatus
from swimcore.replay import replay_session
from swimcore.session import FixedClock, SequenceIdGenerator
from swimcore.session.state import SessionState
from tests.replay._golden_helpers import build_normal_session_batches, flatten
from tests.replay.test_event_batch_contract import SID, env

pytestmark = pytest.mark.replay


def test_error_hierarchy_is_typed() -> None:
    assert issubclass(EventLogError, PersistenceError)
    for cls in (
        EventLogCodecError,
        EventLogWriteError,
        EventLogSyncError,
        CorruptEventLogError,
        TailRepairError,
    ):
        assert issubclass(cls, EventLogError)
    assert issubclass(UnsupportedEventBatchVersionError, EventLogCodecError)
    assert issubclass(InvalidEventBatchRecordError, EventLogCodecError)
    assert issubclass(EventLogDurabilityUncertainError, EventLogSyncError)


def test_write_failure_raises_typed_error_with_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = JsonlSessionEventLog(tmp_path / "s.jsonl", SID)
    log.append_batch([env(1)])

    real_write = os.write
    state = {"written": 0}

    def failing_write(fd: int, data: bytes | memoryview) -> int:
        if state["written"] == 0:
            # write half the buffer, then die — a torn line remains on disk
            view = memoryview(bytes(data))
            half = max(1, len(view) // 2)
            state["written"] = real_write(fd, view[:half])
            raise OSError(28, "injected ENOSPC")
        return real_write(fd, data)

    monkeypatch.setattr("persistence.jsonl_event_log.os.write", failing_write)
    with pytest.raises(EventLogWriteError) as exc_info:
        log.append_batch([env(2, ts=2000, cid="cmd-2")])
    assert isinstance(exc_info.value.__cause__, OSError)
    monkeypatch.undo()

    # The torn tail is on disk: reading without repair refuses, recovery truncates it and
    # the batch can be appended again.
    fresh = JsonlSessionEventLog(log.path, SID)
    with pytest.raises(TailRepairError):
        fresh.read_all()
    recovered = fresh.recover_and_read()
    assert [e.seq for e in recovered.events] == [1]
    assert len(recovered.notices) == 1
    assert fresh.append_batch([env(2, ts=2000, cid="cmd-2")]).status is AppendStatus.APPENDED


def test_durability_uncertain_message_mentions_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = JsonlSessionEventLog(tmp_path / "s.jsonl", SID)

    def fail(fd: int) -> None:
        raise OSError(5, "EIO")

    monkeypatch.setattr("persistence.jsonl_event_log.os.fsync", fail)
    with pytest.raises(EventLogDurabilityUncertainError, match="retry"):
        log.append_batch([env(1)])


# ------------------------------------------------------------------ SessionRecovered (§18)
def test_build_session_recovered_event_is_explicit_and_typed(tmp_path: Path) -> None:
    batches = build_normal_session_batches()
    events = flatten(batches)
    session_id = events[0].sessionId
    assert session_id is not None

    log = JsonlSessionEventLog(tmp_path / "s.jsonl", session_id)
    for batch in batches[:3]:  # create/arm/start persisted, then "crash"
        log.append_batch(batch)
    recovered = log.recover_and_read()
    size_before = log.path.read_bytes()

    marker = build_session_recovered_event(
        session_id=session_id,
        client_command_id="recovery-1",
        last_recovered_seq=recovered.events[-1].seq,
        recovered_event_count=len(recovered.events),
        recovery_reason="process restart",
        clock=FixedClock(99_000),
        id_gen=SequenceIdGenerator("rec"),
    )
    # building the marker touched NOTHING on disk (never auto-appended)
    assert log.path.read_bytes() == size_before
    assert marker.seq == recovered.events[-1].seq + 1
    assert marker.tsMs == 99_000
    assert marker.eventId == "rec-1"

    # replay with the marker: recoveryCount increments, lifecycle unchanged
    without = replay_session(list(recovered.events))
    with_marker = replay_session([*recovered.events, marker])
    assert without.state.recoveryCount == 0
    assert with_marker.state.recoveryCount == 1
    assert with_marker.state.lifecycleState is without.state.lifecycleState is SessionState.RUNNING


def test_session_recovered_can_be_persisted_explicitly(tmp_path: Path) -> None:
    batches = build_normal_session_batches()
    events = flatten(batches[:3])
    session_id = events[0].sessionId
    assert session_id is not None
    log = JsonlSessionEventLog(tmp_path / "s.jsonl", session_id)
    for batch in batches[:3]:
        log.append_batch(batch)
    marker = build_session_recovered_event(
        session_id=session_id,
        client_command_id="recovery-1",
        last_recovered_seq=4,
        recovered_event_count=4,
        recovery_reason="restart",
        clock=FixedClock(50_000),
        id_gen=SequenceIdGenerator("rec"),
    )
    assert log.append_batch([marker]).status is AppendStatus.APPENDED  # explicit decision
    replayed = replay_session(list(log.read_all().events))
    assert replayed.state.recoveryCount == 1
    assert replayed.state.lifecycleState is SessionState.RUNNING
