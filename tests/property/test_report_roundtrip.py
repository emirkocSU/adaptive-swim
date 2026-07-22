from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from analytics.identity import deterministic_report_id
from analytics.serialization import decode_session_report, encode_session_report
from tests.unit._analytics_helpers import report


@given(st.text(min_size=1, max_size=20))
def test_report_identity_helper_is_deterministic(note: str) -> None:
    value = report().model_copy(update={"notes": note})
    assert deterministic_report_id(value) == deterministic_report_id(value)


def test_report_encode_decode_roundtrip() -> None:
    value = report()
    assert decode_session_report(encode_session_report(value)) == value
