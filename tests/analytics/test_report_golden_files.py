from __future__ import annotations

from pathlib import Path

from simulator.harness import SimulationResult

GOLDEN_DIR = Path(__file__).parent / "goldens"
MAPPING = {
    "normal-pace-loss": "normal-pace-loss-report.json",
    "long-stop-mid-length": "long-stop-report.json",
    "coach-continuous-curve-reset": "coach-curve-reset-report.json",
}


def test_committed_report_goldens_are_byte_identical(
    analytics_results: dict[str, SimulationResult],
) -> None:
    for scenario, filename in MAPPING.items():
        assert (
            analytics_results[scenario].sessionReportBytes == (GOLDEN_DIR / filename).read_bytes()
        )
