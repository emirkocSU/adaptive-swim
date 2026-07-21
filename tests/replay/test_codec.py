"""Canonical JSONL codec tests (Commit 7 §7, §20)."""

from __future__ import annotations

import json

import pytest

from contracts.event_log import EventBatchRecord
from persistence.codec import decode_batch, encode_batch
from persistence.errors import (
    EventLogCodecError,
    InvalidEventBatchRecordError,
    UnsupportedEventBatchVersionError,
)
from tests.replay.test_event_batch_contract import env

pytestmark = pytest.mark.replay


def record() -> EventBatchRecord:
    return EventBatchRecord.from_events([env(1), env(2, ts=1500)])


def test_same_record_creates_identical_bytes() -> None:
    assert encode_batch(record()) == encode_batch(record())


def test_utf8_and_exactly_one_lf() -> None:
    line = encode_batch(record())
    assert line.endswith(b"\n") and not line.endswith(b"\n\n")
    assert b"\r" not in line
    text = line.decode("utf-8")  # must be valid UTF-8
    assert not text.startswith("\ufeff")
    assert "\n" not in text[:-1]  # exactly one LF, at the end


def test_sorted_compact_json() -> None:
    text = encode_batch(record()).decode("utf-8").rstrip("\n")
    assert ": " not in text and ", " not in text  # compact separators
    data = json.loads(text)
    assert list(data.keys()) == sorted(data.keys())


def test_round_trip_is_byte_identical() -> None:
    line = encode_batch(record())
    assert encode_batch(decode_batch(line)) == line


def test_decode_accepts_line_without_trailing_newline() -> None:
    line = encode_batch(record())
    assert decode_batch(line[:-1]) == decode_batch(line)


def test_nan_and_infinity_rejected_on_decode() -> None:
    line = encode_batch(record()).decode("utf-8").rstrip("\n")
    for constant in ("NaN", "Infinity", "-Infinity"):
        poisoned = line.replace('"firstSeq":1', f'"firstSeq":1,"x":{constant}')
        with pytest.raises(EventLogCodecError):
            decode_batch(poisoned.encode("utf-8") + b"\n")


def test_invalid_json_wrapped() -> None:
    with pytest.raises(EventLogCodecError) as exc_info:
        decode_batch(b'{"recordType": "EVENT_BATCH", truncated')
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_invalid_utf8_wrapped() -> None:
    with pytest.raises(EventLogCodecError):
        decode_batch(b"\xff\xfe{}")


def test_bom_rejected() -> None:
    line = encode_batch(record())
    with pytest.raises(EventLogCodecError, match="BOM"):
        decode_batch("\ufeff".encode() + line)


def test_unknown_version_rejected() -> None:
    text = encode_batch(record()).decode("utf-8")
    poisoned = text.replace('"recordVersion":"1.0"', '"recordVersion":"9.9"')
    with pytest.raises(UnsupportedEventBatchVersionError):
        decode_batch(poisoned.encode("utf-8"))


def test_wrong_record_type_rejected() -> None:
    text = encode_batch(record()).decode("utf-8")
    poisoned = text.replace('"recordType":"EVENT_BATCH"', '"recordType":"SOMETHING"')
    with pytest.raises(InvalidEventBatchRecordError):
        decode_batch(poisoned.encode("utf-8"))


def test_blank_line_rejected() -> None:
    for blank in (b"", b"\n", b"   ", b"   \n"):
        with pytest.raises(EventLogCodecError):
            decode_batch(blank)


def test_non_object_json_rejected() -> None:
    with pytest.raises(InvalidEventBatchRecordError):
        decode_batch(b"[1,2,3]\n")


def test_pydantic_error_wrapped_not_leaked() -> None:
    text = encode_batch(record()).decode("utf-8")
    poisoned = text.replace('"eventCount":2', '"eventCount":5')
    with pytest.raises(InvalidEventBatchRecordError):
        decode_batch(poisoned.encode("utf-8"))
