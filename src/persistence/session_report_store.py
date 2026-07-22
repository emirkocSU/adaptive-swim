"""Atomic storage adapter for canonical derived report bytes.

The event journal is untouched.  The store validates the 1.1 contract and requires the
incoming bytes to be exactly the canonical encoding before writing.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from contracts.session_report import SessionReportV1_1
from persistence.errors import PersistenceError


class SessionReportStoreError(PersistenceError):
    pass


class SessionReportConflictError(SessionReportStoreError):
    pass


def _canonical_bytes(report: SessionReportV1_1) -> bytes:
    payload = report.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _content_addressed_report_id(report: SessionReportV1_1) -> str:
    payload = report.model_dump(mode="json", exclude_none=False)
    payload.pop("reportId", None)
    identity_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(identity_bytes).hexdigest()


class SessionReportStore:
    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)

    def path_for(self, report_id: str) -> Path:
        return self._directory / f"{report_id}.json"

    def write(self, report_id: str, canonical_bytes: bytes) -> Path:
        try:
            payload = json.loads(canonical_bytes.decode("utf-8"))
            report = SessionReportV1_1.model_validate(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise SessionReportStoreError(
                "report bytes are not valid SessionReport 1.1 JSON"
            ) from exc
        expected = _canonical_bytes(report)
        if expected != canonical_bytes:
            raise SessionReportStoreError("report bytes are valid JSON but are not canonical")
        if report.reportId != report_id:
            raise SessionReportStoreError("reportId in canonical bytes does not match requested id")
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self.path_for(report_id)
        if target.exists():
            existing = target.read_bytes()
            if existing != canonical_bytes:
                raise SessionReportConflictError(
                    f"different content already exists for report id {report_id}"
                )
            return target
        if report.reportId != _content_addressed_report_id(report):
            raise SessionReportStoreError("reportId is not the content-addressed report identity")
        temp = target.with_suffix(".json.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
        fd = os.open(temp, flags, 0o644)
        try:
            view = memoryview(canonical_bytes)
            written = 0
            while written < len(view):
                written += os.write(fd, view[written:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, target)
        return target
