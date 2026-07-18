"""Commit 6 — idempotency and command-id conflict."""

from __future__ import annotations

import pytest

from swimcore.session import CommandIdConflictError
from tests.unit._session_helpers import record_split, started


def test_duplicate_identical_command_produces_no_duplicate_mutation() -> None:
    agg, clk = started()
    e1 = agg.handle(record_split(agg, 0, ts=40000, cid="sp"))
    seq_after_first = agg._events._seq
    e2 = agg.handle(record_split(agg, 0, ts=40000, cid="sp"))
    assert [e.eventId for e in e1] == [e.eventId for e in e2]
    assert agg._events._seq == seq_after_first
    assert len(agg.recordedSplits) == 1


def test_same_client_command_id_different_content_is_conflict() -> None:
    agg, clk = started()
    agg.handle(record_split(agg, 0, ts=40000, cid="sp"))
    with pytest.raises(CommandIdConflictError):
        agg.handle(record_split(agg, 0, ts=41000, cid="sp"))


def test_event_seq_remains_monotonic() -> None:
    agg, clk = started()
    all_events = []
    for i in range(3):
        all_events += agg.handle(record_split(agg, i, ts=40000 * (i + 1), cid=f"sp{i}"))
    seqs = [e.seq for e in all_events]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
