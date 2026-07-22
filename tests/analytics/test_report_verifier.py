from __future__ import annotations

from simulator.harness import SimulationResult
from swimtools.verify_report import main


def test_report_verifier_accepts_matching_journal(
    normal_report_result: SimulationResult,
) -> None:
    assert (
        main(
            [
                "--report",
                str(normal_report_result.sessionReportPath),
                "--journal",
                str(normal_report_result.journalPath),
            ]
        )
        == 0
    )
