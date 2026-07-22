from __future__ import annotations

from analytics.serialization import decode_session_report, encode_session_report
from tests.unit._analytics_helpers import report


def test_canonical_report_serialization_is_bit_identical() -> None:
    value = report()
    encoded = encode_session_report(value)
    assert encoded == encode_session_report(value)
    assert decode_session_report(encoded) == value
    assert encoded.endswith(b"}")
    assert b"\n" not in encoded
