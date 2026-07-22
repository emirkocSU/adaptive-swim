"""JSONL event journal append tests (Commit 7 §8, §20)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from persistence.errors import (
    EventLogDuplicateEventIdError,
    EventLogSequenceError,
    EventLogSessionMismatchError,
    EventLogTimestampError,
)
from persistence.jsonl_event_log import JsonlSessionEventLog
from persistence.types import AppendStatus
from tests.replay.test_event_batch_contract import SID, env

pytestmark = pytest.mark.replay


def log_at(tmp_path: Path) -> JsonlSessionEventLog:
    return JsonlSessionEventLog(tmp_path / "session.jsonl", SID)


def test_append_creates_file_and_reports_success(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    assert not log.path.exists()
    result = log.append_batch([env(1), env(2, ts=1500)])
    assert log.path.exists()
    assert result.status is AppendStatus.APPENDED
    assert result.fsynced is True
    assert (result.firstSeq, result.lastSeq, result.eventCount) == (1, 2, 2)
    assert result.bytesWritten == log.path.stat().st_size


def test_one_command_creates_one_line(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1), env(2, ts=1500)])  # two events, ONE command
    log.append_batch([env(3, ts=2000, cid="cmd-2")])
    lines = log.path.read_bytes().split(b"\n")
    assert lines[-1] == b""  # file ends with newline
    assert len(lines) - 1 == 2  # one line per command batch


def test_multiple_batches_preserve_order(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1)])
    log.append_batch([env(2, ts=1500, cid="cmd-2")])
    log.append_batch([env(3, ts=2000, cid="cmd-3")])
    result = log.read_all()
    assert [b.clientCommandId for b in result.batches] == ["cmd-1", "cmd-2", "cmd-3"]
    assert [e.seq for e in result.events] == [1, 2, 3]


def test_fsync_occurs_before_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real_fsync = os.fsync

    def spy_fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    monkeypatch.setattr("persistence.jsonl_event_log.os.fsync", spy_fsync)
    log = log_at(tmp_path)
    result = log.append_batch([env(1)])
    assert result.fsynced is True
    assert "fsync" in calls  # fsync happened before append_batch returned


def test_partial_os_write_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """os.write may write fewer bytes than asked; the loop must still write everything."""
    real_write = os.write

    def one_byte_write(fd: int, data: bytes | memoryview) -> int:
        view = memoryview(bytes(data))
        return real_write(fd, view[:1])  # force worst-case partial writes

    monkeypatch.setattr("persistence.jsonl_event_log.os.write", one_byte_write)
    log = log_at(tmp_path)
    result = log.append_batch([env(1), env(2, ts=1500)])
    assert result.status is AppendStatus.APPENDED
    monkeypatch.undo()
    reread = JsonlSessionEventLog(log.path, SID).read_all()
    assert [e.seq for e in reread.events] == [1, 2]


def test_eintr_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_write = os.write
    interrupted = {"n": 0}

    def flaky_write(fd: int, data: bytes | memoryview) -> int:
        if interrupted["n"] < 3:
            interrupted["n"] += 1
            raise InterruptedError("EINTR")
        return real_write(fd, data)

    monkeypatch.setattr("persistence.jsonl_event_log.os.write", flaky_write)
    log = log_at(tmp_path)
    assert log.append_batch([env(1)]).status is AppendStatus.APPENDED
    assert interrupted["n"] == 3


@pytest.mark.skipif(os.name == "nt", reason="Windows does not support directory fsync")
def test_new_file_parent_directory_synced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    synced_dirs: list[bool] = []
    real_fsync = os.fsync
    real_open = os.open

    opened_dirs: set[int] = set()

    def spy_open(path: object, flags: int, mode: int = 0o777) -> int:
        fd = real_open(path, flags, mode)  # type: ignore[arg-type]
        if Path(str(path)).is_dir():
            opened_dirs.add(fd)
        return fd

    def spy_fsync(fd: int) -> None:
        if fd in opened_dirs:
            synced_dirs.append(True)
        real_fsync(fd)

    monkeypatch.setattr("persistence.jsonl_event_log.os.open", spy_open)
    monkeypatch.setattr("persistence.jsonl_event_log.os.fsync", spy_fsync)
    log = log_at(tmp_path)
    log.append_batch([env(1)])
    assert synced_dirs, "parent directory was not fsync'ed after creating the journal file"


def test_session_mismatch_rejected(tmp_path: Path) -> None:
    log = JsonlSessionEventLog(tmp_path / "other.jsonl", "session-OTHER")
    with pytest.raises(EventLogSessionMismatchError):
        log.append_batch([env(1)])


def test_seq_gap_rejected(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1)])
    with pytest.raises(EventLogSequenceError):
        log.append_batch([env(3, ts=2000, cid="cmd-2")])


def test_timestamp_regression_rejected(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1, ts=5000)])
    with pytest.raises(EventLogTimestampError):
        log.append_batch([env(2, ts=1000, cid="cmd-2")])


def test_duplicate_event_id_rejected(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1, event_id="shared")])
    with pytest.raises(EventLogDuplicateEventIdError):
        log.append_batch([env(2, ts=2000, cid="cmd-2", event_id="shared")])


def test_reopened_log_continues_from_disk_state(tmp_path: Path) -> None:
    log = log_at(tmp_path)
    log.append_batch([env(1)])
    reopened = JsonlSessionEventLog(log.path, SID)
    assert reopened.last_seq == 1
    reopened.append_batch([env(2, ts=1500, cid="cmd-2")])
    assert [e.seq for e in reopened.read_all().events] == [1, 2]
