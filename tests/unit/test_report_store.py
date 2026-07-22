from __future__ import annotations

from pathlib import Path

import pytest

from analytics.serialization import encode_session_report
from persistence.session_report_store import (
    SessionReportConflictError,
    SessionReportStore,
    SessionReportStoreError,
)
from tests.unit._analytics_helpers import report


def test_report_store_is_idempotent_and_conflict_safe(tmp_path: Path) -> None:
    value = report()
    data = encode_session_report(value)
    store = SessionReportStore(tmp_path)
    first = store.write(value.reportId, data)
    second = store.write(value.reportId, data)
    assert first == second
    with pytest.raises(SessionReportConflictError):
        store.write(value.reportId, data.replace(b'"notes":null', b'"notes":"changed"'))


def test_report_store_rejects_canonical_bytes_with_forged_identity(tmp_path: Path) -> None:
    value = report().model_copy(update={"reportId": "forged-report-id"})
    data = encode_session_report(value)
    with pytest.raises(SessionReportStoreError, match="content-addressed"):
        SessionReportStore(tmp_path).write(value.reportId, data)
