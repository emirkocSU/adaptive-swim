"""Canonical JSONL codec for EventBatchRecord lines (Commit 7).

There is exactly one authoritative encoding: UTF-8, no BOM, no pretty-print, stable key
ordering, compact separators, ``allow_nan=False``, and exactly one platform-independent
``\\n`` terminator. The same record always encodes to byte-for-byte identical output.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from contracts.event_log import EventBatchRecord
from contracts.version import SUPPORTED_EVENT_BATCH_RECORD_VERSIONS
from persistence.errors import (
    EventLogCodecError,
    InvalidEventBatchRecordError,
    UnsupportedEventBatchVersionError,
)

_NEWLINE = b"\n"
_BOM = "\ufeff"


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed in an event log")


def encode_batch(record: EventBatchRecord) -> bytes:
    """Encode one record as one canonical JSONL line (terminated by exactly one LF)."""
    try:
        payload = record.model_dump(mode="json")
        text = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (ValueError, TypeError) as exc:
        raise EventLogCodecError(f"cannot encode EventBatchRecord: {exc}") from exc
    return text.encode("utf-8") + _NEWLINE


def decode_batch(raw_line: bytes) -> EventBatchRecord:
    """Decode one JSONL line (with or without its trailing LF) back into a record.

    Raw ``JSONDecodeError`` / ``UnicodeDecodeError`` / Pydantic errors never escape; they
    are wrapped in the typed codec errors with ``__cause__`` preserved.
    """
    line = raw_line[:-1] if raw_line.endswith(_NEWLINE) else raw_line
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EventLogCodecError(f"line is not valid UTF-8: {exc}") from exc
    if text.startswith(_BOM):
        raise EventLogCodecError("line starts with a UTF-8 BOM (not allowed)")
    if not text.strip():
        raise EventLogCodecError("empty or whitespace-only line")
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except ValueError as exc:  # includes json.JSONDecodeError and _reject_constant
        raise EventLogCodecError(f"line is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidEventBatchRecordError(f"expected a JSON object, got {type(data).__name__}")
    version = data.get("recordVersion")
    if version not in SUPPORTED_EVENT_BATCH_RECORD_VERSIONS:
        raise UnsupportedEventBatchVersionError(
            f"unsupported recordVersion {version!r} "
            f"(supported: {sorted(SUPPORTED_EVENT_BATCH_RECORD_VERSIONS)})"
        )
    if data.get("recordType") != "EVENT_BATCH":
        raise InvalidEventBatchRecordError(
            f"unexpected recordType {data.get('recordType')!r} (expected 'EVENT_BATCH')"
        )
    try:
        return EventBatchRecord.model_validate(data)
    except ValidationError as exc:
        raise InvalidEventBatchRecordError(f"invalid EventBatchRecord: {exc}") from exc
