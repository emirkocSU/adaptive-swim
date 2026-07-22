"""Canonical JSON encoding for SessionReport 1.1."""

from __future__ import annotations

import hashlib
import json

from contracts.session_report import SessionReportV1_1


def encode_session_report(report: SessionReportV1_1) -> bytes:
    """Encode as deterministic UTF-8 JSON (sorted keys, compact, no NaN/Infinity)."""
    payload = report.model_dump(mode="json", exclude_none=False)
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return rendered.encode("utf-8")


def decode_session_report(data: bytes) -> SessionReportV1_1:
    value = json.loads(data.decode("utf-8"))
    return SessionReportV1_1.model_validate(value)


def session_report_sha256(report: SessionReportV1_1) -> str:
    return hashlib.sha256(encode_session_report(report)).hexdigest()
