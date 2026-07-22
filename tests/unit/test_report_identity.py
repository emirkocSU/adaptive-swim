from __future__ import annotations

from analytics.identity import deterministic_report_id
from tests.unit._analytics_helpers import report


def test_report_identity_is_deterministic_and_content_addressed() -> None:
    first = report()
    second = report()
    assert first.reportId == second.reportId
    assert deterministic_report_id(first) == first.reportId
    changed = first.model_copy(update={"notes": "different deterministic content"})
    assert deterministic_report_id(changed) != first.reportId
