"""Phase 1 vertical-slice runner CLI (ADR-041).

Thin orchestration over :mod:`e2e`; it owns no domain rules and no verification logic.

    python -m swimtools.run_e2e --list
    python -m swimtools.run_e2e --case normal-continuous-completion --seed 42 --output ./out
    python -m swimtools.run_e2e --all --output ./e2e-all
    python -m swimtools.run_e2e --all --output ./e2e-all --format json --fail-fast

Exit codes: ``0`` when every case passed every cross-component invariant, ``1`` when a check
failed, ``2`` for invalid CLI input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from e2e.cases import CASE_BY_ID, REQUIRED_CASE_IDS, build_all_cases
from e2e.errors import E2EError
from e2e.manifest import CheckStatus
from e2e.runner import run_phase1_vertical_slice
from e2e.types import Phase1E2EResult

EXIT_OK = 0
EXIT_CHECKS_FAILED = 1
EXIT_INVALID_INPUT = 2


def _summary(result: Phase1E2EResult) -> dict[str, object]:
    manifest = result.verificationManifest
    return {
        "caseId": result.caseId,
        "caseVersion": result.caseVersion,
        "seed": result.seed,
        "runId": result.runId,
        "manifestId": manifest.manifestId,
        "eventCount": result.eventCount,
        "batchCount": manifest.batchCount,
        "journalSha256": result.journalSha256,
        "reportSha256": result.sessionReportSha256,
        "manifestSha256": result.verificationManifestSha256,
        "reportId": result.sessionReport.reportId,
        "liveReplayMatch": result.liveReplayMatch,
        "checkCount": len(manifest.checks),
        "failedCheckCount": sum(1 for check in manifest.checks if check.status is CheckStatus.FAIL),
        "allChecksPassed": result.allChecksPassed,
        "warnings": list(result.warnings),
    }


def _print_text(summary: dict[str, object]) -> None:
    status = "PASS" if summary["allChecksPassed"] else "FAIL"
    print(f"[{status}] {summary['caseId']} (seed={summary['seed']})")
    for key in (
        "runId",
        "manifestId",
        "eventCount",
        "batchCount",
        "journalSha256",
        "reportSha256",
        "manifestSha256",
        "reportId",
        "liveReplayMatch",
        "checkCount",
        "failedCheckCount",
    ):
        print(f"  {key}: {summary[key]}")
    warnings = summary["warnings"]
    if isinstance(warnings, list):
        for warning in warnings:
            print(f"  warning: {warning}")


def _list_cases() -> int:
    for case in build_all_cases():
        tag = "required" if case.caseId in REQUIRED_CASE_IDS else "failure-scenario"
        print(f"{case.caseId}\t[{tag}]\tseed={case.seed}\t{case.description}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="swimtools.run_e2e",
        description="Run the Phase 1 full vertical-slice verification matrix",
    )
    parser.add_argument("--list", action="store_true", help="list available cases")
    parser.add_argument("--case", default=None, help="case id to run")
    parser.add_argument("--all", action="store_true", help="run every case")
    parser.add_argument("--seed", type=int, default=None, help="override the case seed")
    parser.add_argument("--output", type=Path, default=None, help="output bundle directory")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-fast", action="store_true", help="stop at the first failing case")
    args = parser.parse_args(argv)

    if args.list:
        return _list_cases()
    if args.all and args.case is not None:
        parser.error("--all and --case are mutually exclusive")
    if not args.all and args.case is None:
        parser.error("--case or --all is required unless --list is given")
    if args.output is None:
        parser.error("--output is required")

    if args.all:
        cases = build_all_cases()
    else:
        builder = CASE_BY_ID.get(args.case)
        if builder is None:
            print(f"unknown case: {args.case}", file=sys.stderr)
            print(f"available: {', '.join(sorted(CASE_BY_ID))}", file=sys.stderr)
            return EXIT_INVALID_INPUT
        cases = [builder()]

    root = Path(args.output)
    summaries: list[dict[str, object]] = []
    exit_code = EXIT_OK
    for case in cases:
        directory = root / case.caseId if len(cases) > 1 else root
        try:
            result = run_phase1_vertical_slice(
                case=case, output_directory=directory, seed=args.seed
            )
        except E2EError as exc:
            print(f"{case.caseId}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_CHECKS_FAILED
        summary = _summary(result)
        summaries.append(summary)
        if not result.allChecksPassed:
            exit_code = EXIT_CHECKS_FAILED
            failed = [
                check
                for check in result.verificationManifest.checks
                if check.status is CheckStatus.FAIL
            ]
            for check in failed:
                print(
                    f"{case.caseId}: FAILED {check.checkId} "
                    f"(expected={check.expected}, actual={check.actual})",
                    file=sys.stderr,
                )
            if args.fail_fast:
                break

    if args.format == "json":
        print(json.dumps(summaries, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for summary in summaries:
            _print_text(summary)
        passed = sum(1 for item in summaries if item["allChecksPassed"])
        print(f"{passed}/{len(summaries)} case(s) passed every invariant")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
