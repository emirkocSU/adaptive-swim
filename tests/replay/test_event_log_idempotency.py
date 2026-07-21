"""Idempotent exact-batch retry and conflict tests (Commit 7 §9, §20, §26)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from persistence.errors import EventLogConflictError, EventLogDurabilityUncertainError
from persistence.jsonl_event_log import JsonlSessionEventLog
from persistence.types import AppendStatus
from tests.replay.test_event_batch_contract import SID, env

pytestmark = pytest.mark.replay


def log_at(tmp_path: Path) -> JsonlSessionEventLog:
    return JsonlSessionEventLog(tmp_path / "session.jsonl", SID)


def test_exact_duplicate_returns_already_present(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    batch = [env(1), env(2, ts=1500)]
    first = log.append_batch(batch)
    second = log.append_batch(batch)
    assert first.status is AppendStatus.APPENDED
    assert second.status is AppendStatus.ALREADY_PRESENT
    assert second.fsynced is True
    assert second.bytesWritten == 0


def test_exact_duplicate_does_not_append_another_line(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    batch = [env(1)]
    log.append_batch(batch)
    size_before = log.path.stat().st_size
    log.append_batch(batch)
    log.append_batch(batch)
    assert log.path.stat().st_size == size_before
    assert log.path.read_bytes().count(b"\n") == 1


def test_same_seq_with_different_content_conflicts(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1, ts=1000)])
    with pytest.raises(EventLogConflictError):
        log.append_batch([env(1, ts=9999, cid="cmd-other")])


def test_same_command_id_with_different_content_conflicts(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1, ts=1000)])
    with pytest.raises(EventLogConflictError):
        log.append_batch([env(2, ts=2000)])  # same cid "cmd-1", different content


def test_partial_overlap_conflicts(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1), env(2, ts=1500)])
    with pytest.raises(EventLogConflictError):
        # overlaps persisted seq 2 and adds seq 3 — a partial overlap, not an exact retry
        log.append_batch([env(2, ts=1500, cid="cmd-2"), env(3, ts=1600, cid="cmd-2")])


def test_duplicate_event_id_with_same_command_id_conflicts(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1, event_id="shared")])
    with pytest.raises(EventLogConflictError):
        # same clientCommandId, different content (fresh seq + reused eventId)
        log.append_batch([env(2, ts=1500, cid="cmd-1", event_id="shared")])


def test_fsync_failure_retry_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """§26: inject fsync failure → durability-uncertain → exact retry → ALREADY_PRESENT."""
    log = log_at(tmp_path)
    batch = [env(1), env(2, ts=1500)]

    real_fsync = os.fsync
    fail = {"active": True}

    def failing_fsync(fd: int) -> None:
        if fail["active"]:
            raise OSError(5, "injected fsync failure")
        real_fsync(fd)

    monkeypatch.setattr("persistence.jsonl_event_log.os.fsync", failing_fsync)
    with pytest.raises(EventLogDurabilityUncertainError):
        log.append_batch(batch)

    # the full line IS on disk exactly once
    assert log.path.read_bytes().count(b"\n") == 1

    # retry with fsync healthy again: no duplicate line, re-fsync, ALREADY_PRESENT
    fail["active"] = False
    result = log.append_batch(batch)
    assert result.status is AppendStatus.ALREADY_PRESENT
    assert result.fsynced is True
    assert log.path.read_bytes().count(b"\n") == 1

    # journal still fully readable and consistent
    reread = JsonlSessionEventLog(log.path, SID).read_all()
    assert [e.seq for e in reread.events] == [1, 2]


def test_fsync_failure_line_is_never_auto_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = log_at(tmp_path)

    def always_fail(fd: int) -> None:
        raise OSError(5, "injected")

    monkeypatch.setattr("persistence.jsonl_event_log.os.fsync", always_fail)
    with pytest.raises(EventLogDurabilityUncertainError):
        log.append_batch([env(1)])
    monkeypatch.undo()
    # the complete line was NOT removed
    assert log.path.read_bytes().count(b"\n") == 1
    assert [e.seq for e in JsonlSessionEventLog(log.path, SID).read_all().events] == [1]


def test_retry_after_durability_uncertain_allows_next_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = log_at(tmp_path)
    real_fsync = os.fsync
    fail = {"active": True}

    def flaky(fd: int) -> None:
        if fail["active"]:
            raise OSError(5, "injected")
        real_fsync(fd)

    monkeypatch.setattr("persistence.jsonl_event_log.os.fsync", flaky)
    with pytest.raises(EventLogDurabilityUncertainError):
        log.append_batch([env(1)])
    fail["active"] = False
    assert log.append_batch([env(1)]).status is AppendStatus.ALREADY_PRESENT
    assert log.append_batch([env(2, ts=1500, cid="cmd-2")]).status is AppendStatus.APPENDED
    assert [e.seq for e in log.read_all().events] == [1, 2]
