"""Property-based Commit 7 invariants (§21): codec, journal, replay durations."""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contracts.enums import EventType
from contracts.event_log import EventBatchRecord
from contracts.events import EventEnvelope, SessionArmedPayload
from persistence.codec import decode_batch, encode_batch
from persistence.jsonl_event_log import JsonlSessionEventLog
from persistence.types import AppendStatus
from swimcore.replay import replay_session
from tests.replay._stream_helpers import POOL, StreamBuilder

pytestmark = pytest.mark.property

SID = "session-p"


# ------------------------------------------------------------------ strategies
@st.composite
def event_batches(draw: st.DrawFn) -> list[list[EventEnvelope]]:
    """A structurally valid sequence of command batches with contiguous seq."""
    n_batches = draw(st.integers(min_value=1, max_value=5))
    batches: list[list[EventEnvelope]] = []
    seq = 0
    ts = 0
    for b in range(n_batches):
        size = draw(st.integers(min_value=1, max_value=3))
        batch: list[EventEnvelope] = []
        for _ in range(size):
            seq += 1
            ts += draw(st.integers(min_value=0, max_value=10_000))
            batch.append(
                EventEnvelope(
                    eventId=f"evt-{seq}",
                    seq=seq,
                    sessionId=SID,
                    type=EventType.SessionArmed,
                    tsMs=ts,
                    producer="prop",
                    clientCommandId=f"cmd-{b}",
                    payload=SessionArmedPayload(sessionId=SID),
                )
            )
        batches.append(batch)
    return batches


@st.composite
def session_scenarios(draw: st.DrawFn) -> StreamBuilder:
    """A valid running session with optional pause and StopPause intervals + splits."""
    b = StreamBuilder().running(0)
    t = 0
    splits = 0
    stops = 0
    for _ in range(draw(st.integers(min_value=0, max_value=4))):
        action = draw(st.sampled_from(["split", "pause", "stop"]))
        if action == "split":
            t += draw(st.integers(min_value=1, max_value=20_000))
            b.split(splits, t)
            splits += 1
        elif action == "pause":
            t += draw(st.integers(min_value=1, max_value=10_000))
            pause_start = t
            t += draw(st.integers(min_value=0, max_value=15_000))
            b.paused(pause_start).resumed(t)
        else:
            started = t + draw(st.integers(min_value=1, max_value=5_000))
            confirmed = started + draw(st.integers(min_value=0, max_value=11_000))
            ended = confirmed + draw(st.integers(min_value=0, max_value=20_000))
            stops += 1
            iid = f"{b.session_id}-stop-{stops}"
            b.stop_started(started_at=started, confirmed_at=confirmed, interval_id=iid)
            b.stop_resolved(started_at=started, ended_at=ended, interval_id=iid)
            t = ended
    if draw(st.booleans()):
        t += draw(st.integers(min_value=0, max_value=10_000))
        b.completed(t)
    return b


# ------------------------------------------------------------------ codec
@given(event_batches())
@settings(max_examples=50, deadline=None)
def test_codec_round_trip_is_byte_identical(batches: list[list[EventEnvelope]]) -> None:
    for batch in batches:
        record = EventBatchRecord.from_events(batch)
        line = encode_batch(record)
        assert encode_batch(decode_batch(line)) == line


@given(event_batches())
@settings(max_examples=50, deadline=None)
def test_valid_batch_flattening_keeps_contiguous_seq(
    batches: list[list[EventEnvelope]],
) -> None:
    records = [EventBatchRecord.from_events(b) for b in batches]
    flat = [e for r in records for e in r.events]
    assert [e.seq for e in flat] == list(range(1, len(flat) + 1))


# ------------------------------------------------------------------ journal
@given(event_batches())
@settings(max_examples=25, deadline=None)
def test_journal_read_order_equals_append_order(batches: list[list[EventEnvelope]]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = JsonlSessionEventLog(Path(tmp) / "s.jsonl", SID)
        for batch in batches:
            log.append_batch(batch)
        result = log.read_all()
        assert [b.clientCommandId for b in result.batches] == [
            batch[0].clientCommandId for batch in batches
        ]
        assert [e.seq for e in result.events] == [e.seq for b in batches for e in b]


@given(event_batches(), st.integers(min_value=1, max_value=3))
@settings(max_examples=25, deadline=None)
def test_exact_duplicate_append_never_increases_line_count(
    batches: list[list[EventEnvelope]], retries: int
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = JsonlSessionEventLog(Path(tmp) / "s.jsonl", SID)
        for batch in batches:
            log.append_batch(batch)
        lines_before = log.path.read_bytes().count(b"\n")
        for _ in range(retries):
            for batch in batches:
                assert log.append_batch(batch).status is AppendStatus.ALREADY_PRESENT
        assert log.path.read_bytes().count(b"\n") == lines_before


@given(event_batches(), st.binary(min_size=1, max_size=40))
@settings(max_examples=25, deadline=None)
def test_tail_repair_never_removes_bytes_before_last_complete_newline(
    batches: list[list[EventEnvelope]], garbage: bytes
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = JsonlSessionEventLog(Path(tmp) / "s.jsonl", SID)
        for batch in batches:
            log.append_batch(batch)
        intact = log.path.read_bytes()
        tail = garbage.replace(b"\n", b"?")  # keep the garbage after the last newline
        log.path.write_bytes(intact + tail)
        fresh = JsonlSessionEventLog(log.path, SID)
        # even a rejected/corrupt read must not modify the intact prefix
        with contextlib.suppress(Exception):
            fresh.recover_and_read()
        assert log.path.read_bytes()[: len(intact)] == intact


# ------------------------------------------------------------------ replay
@given(session_scenarios())
@settings(max_examples=60, deadline=None)
def test_duration_invariants_hold(builder: StreamBuilder) -> None:
    state = replay_session(builder.events).state
    assert state.activeDurationMs >= 0
    assert state.stoppedDurationMs >= 0
    assert state.lifecyclePausedDurationMs >= 0
    assert state.elapsedDurationMs == state.activeDurationMs + state.stoppedDurationMs
    assert state.wallDurationMs == state.elapsedDurationMs + state.lifecyclePausedDurationMs


@given(session_scenarios())
@settings(max_examples=40, deadline=None)
def test_replay_same_events_twice_returns_equal_state(builder: StreamBuilder) -> None:
    assert replay_session(builder.events) == replay_session(builder.events)


@given(session_scenarios())
@settings(max_examples=40, deadline=None)
def test_completed_stop_pause_intervals_never_overlap(builder: StreamBuilder) -> None:
    stops = replay_session(builder.events).state.completedStopPauses
    for earlier, later in zip(stops, stops[1:], strict=False):
        assert earlier.endedAtMs is not None
        assert earlier.endedAtMs <= later.startedAtMs


@given(session_scenarios())
@settings(max_examples=40, deadline=None)
def test_official_completed_distance_is_pool_length_multiple(builder: StreamBuilder) -> None:
    state = replay_session(builder.events).state
    assert state.officialCompletedDistanceM is not None
    assert state.officialCompletedDistanceM == state.officialCompletedLengthCount * POOL
    assert float(state.officialCompletedDistanceM) % POOL == 0.0


@given(session_scenarios())
@settings(max_examples=40, deadline=None)
def test_replay_never_mutates_input_events(builder: StreamBuilder) -> None:
    before = [e.model_dump(mode="json") for e in builder.events]
    replay_session(builder.events)
    assert [e.model_dump(mode="json") for e in builder.events] == before
