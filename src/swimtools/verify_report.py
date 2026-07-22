"""Verify a deterministic report against its authoritative journal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from analytics.identity import deterministic_report_id, event_digest_sha256
from analytics.serialization import decode_session_report, encode_session_report
from swimtools._report_io import read_journal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swimtools.verify_report")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw = args.report.read_bytes()
        report = decode_session_report(raw)
        if encode_session_report(report) != raw:
            raise ValueError("report file is valid JSON but not canonical report bytes")
        events = read_journal(args.journal)
        digest = event_digest_sha256(events)
        if report.sessionId != events[0].sessionId:
            raise ValueError("session id mismatch")
        if report.createdFromLastSeq != events[-1].seq:
            raise ValueError("last event sequence mismatch")
        if report.provenance.eventDigestSha256 != digest:
            raise ValueError("event digest mismatch")
        expected_id = deterministic_report_id(report)
        if report.reportId != expected_id:
            raise ValueError("deterministic report id mismatch")
        print(f"report verified: {report.reportId}")
        return 0
    except Exception as exc:
        print(f"report verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
