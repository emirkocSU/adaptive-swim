from __future__ import annotations

import hashlib

from analytics import decode_session_report, encode_session_report
from simulator.harness import SimulationResult


def test_report_identity_bytes_and_roundtrip(
    normal_report_result: SimulationResult,
) -> None:
    report = normal_report_result.sessionReport
    first = encode_session_report(report)
    second = encode_session_report(report)
    assert first == second == normal_report_result.sessionReportBytes
    assert hashlib.sha256(first).hexdigest() == normal_report_result.sessionReportSha256
    assert decode_session_report(first) == report
    assert b"NaN" not in first and b"Infinity" not in first
