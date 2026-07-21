"""Tail recovery and corruption tests (Commit 7 §11, §20, §26)."""

from __future__ import annotations

from pathlib import Path

import pytest

from persistence.errors import CorruptEventLogError, TailRepairError
from persistence.jsonl_event_log import JsonlSessionEventLog
from persistence.types import AppendStatus, LogTailTruncated, MissingFinalNewlineRepaired
from tests.replay.test_event_batch_contract import SID, env

pytestmark = pytest.mark.replay


def make_log_with(tmp_path: Path, n: int) -> JsonlSessionEventLog:
    log = JsonlSessionEventLog(tmp_path / "session.jsonl", SID)
    for i in range(1, n + 1):
        log.append_batch([env(i, ts=i * 1000, cid=f"cmd-{i}")])
    return log


def test_valid_complete_log_unchanged(tmp_path: Path) -> None:
    log = make_log_with(tmp_path, 3)
    before = log.path.read_bytes()
    result = log.recover_and_read()
    assert log.path.read_bytes() == before
    assert result.notices == ()
    assert [e.seq for e in result.events] == [1, 2, 3]


def test_valid_final_json_without_newline_retained(tmp_path: Path) -> None:
    log = make_log_with(tmp_path, 2)
    data = log.path.read_bytes()
    assert data.endswith(b"\n")
    log.path.write_bytes(data[:-1])  # strip the final newline only
    # read WITHOUT repair: record accepted, file untouched
    fresh = JsonlSessionEventLog(log.path, SID)
    result = fresh.read_all(repair_tail=False)
    assert [e.seq for e in result.events] == [1, 2]
    assert result.notices == ()
    assert log.path.read_bytes() == data[:-1]
    # repair mode: ONLY a newline is appended; LogTailTruncated is NOT used
    repaired = fresh.recover_and_read()
    assert [e.seq for e in repaired.events] == [1, 2]
    assert repaired.notices == (MissingFinalNewlineRepaired(originalSizeBytes=len(data) - 1),)
    assert log.path.read_bytes() == data


def test_partial_final_json_truncated_with_exact_notice(tmp_path: Path) -> None:
    """§26 partial tail: two valid batches + half of a third → recovery keeps the two."""
    log = make_log_with(tmp_path, 2)
    intact = log.path.read_bytes()
    third_line = b'{"recordType":"EVENT_BATCH","recordVersion":"1.0","sess'  # torn mid-write
    log.path.write_bytes(intact + third_line)

    fresh = JsonlSessionEventLog(log.path, SID)
    result = fresh.recover_and_read()
    assert [e.seq for e in result.events] == [1, 2]  # first two batches kept
    assert result.notices == (
        LogTailTruncated(
            originalSizeBytes=len(intact) + len(third_line),
            recoveredSizeBytes=len(intact),
            truncatedByteCount=len(third_line),
            truncateOffset=len(intact),
        ),
    )
    assert log.path.read_bytes() == intact  # previous complete batches never removed
    # §26: the third batch can be appended again afterwards
    assert fresh.append_batch([env(3, ts=3000, cid="cmd-3")]).status is AppendStatus.APPENDED
    assert [e.seq for e in fresh.read_all().events] == [1, 2, 3]


def test_read_all_without_repair_refuses_to_drop_partial_tail(tmp_path: Path) -> None:
    log = make_log_with(tmp_path, 1)
    intact = log.path.read_bytes()
    log.path.write_bytes(intact + b'{"half')
    fresh = JsonlSessionEventLog(log.path, SID)
    with pytest.raises(TailRepairError):
        fresh.read_all(repair_tail=False)
    assert log.path.read_bytes() == intact + b'{"half'  # untouched


def test_repair_idempotent(tmp_path: Path) -> None:
    log = make_log_with(tmp_path, 2)
    intact = log.path.read_bytes()
    log.path.write_bytes(intact + b'{"torn')
    fresh = JsonlSessionEventLog(log.path, SID)
    first = fresh.recover_and_read()
    assert len(first.notices) == 1
    second = fresh.recover_and_read()
    third = fresh.recover_and_read()
    assert second.notices == () and third.notices == ()
    assert log.path.read_bytes() == intact


def test_middle_corruption_rejected_never_skipped(tmp_path: Path) -> None:
    """§26 middle corruption: recovery must NOT skip to the third line."""
    log = make_log_with(tmp_path, 3)
    lines = log.path.read_bytes().split(b"\n")
    corrupted = bytearray(lines[1])
    corrupted[5] = (corrupted[5] + 1) % 256  # flip one byte in the SECOND line
    lines[1] = bytes(corrupted)
    log.path.write_bytes(b"\n".join(lines))
    fresh = JsonlSessionEventLog(log.path, SID)
    with pytest.raises(CorruptEventLogError):
        fresh.recover_and_read()
    with pytest.raises(CorruptEventLogError):
        fresh.read_all()


def test_complete_invalid_final_line_rejected(tmp_path: Path) -> None:
    """A newline-terminated invalid final line is corruption, not a partial tail."""
    log = make_log_with(tmp_path, 2)
    log.path.write_bytes(log.path.read_bytes() + b'{"broken": true}\n')
    fresh = JsonlSessionEventLog(log.path, SID)
    with pytest.raises(CorruptEventLogError):
        fresh.recover_and_read()


def test_valid_json_invalid_record_tail_is_corruption(tmp_path: Path) -> None:
    """A fully-parsed but invalid record without newline is not a torn write."""
    log = make_log_with(tmp_path, 1)
    log.path.write_bytes(
        log.path.read_bytes() + b'{"recordType":"EVENT_BATCH","recordVersion":"1.0"}'
    )
    fresh = JsonlSessionEventLog(log.path, SID)
    with pytest.raises(CorruptEventLogError):
        fresh.recover_and_read()


def test_blank_line_rejected(tmp_path: Path) -> None:
    log = make_log_with(tmp_path, 2)
    lines = log.path.read_bytes().split(b"\n")
    with_blank = lines[0] + b"\n\n" + lines[1] + b"\n"
    log.path.write_bytes(with_blank)
    fresh = JsonlSessionEventLog(log.path, SID)
    with pytest.raises(CorruptEventLogError, match="blank"):
        fresh.read_all()


def test_previous_complete_batch_never_removed_by_repair(tmp_path: Path) -> None:
    log = make_log_with(tmp_path, 5)
    intact = log.path.read_bytes()
    log.path.write_bytes(intact + b"garbage-without-newline")
    fresh = JsonlSessionEventLog(log.path, SID)
    fresh.recover_and_read()
    assert log.path.read_bytes() == intact  # byte-for-byte: nothing before the tail moved


def test_empty_file_reads_empty(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    path.write_bytes(b"")
    log = JsonlSessionEventLog(path, SID)
    result = log.read_all()
    assert result.batches == () and result.events == () and result.notices == ()
