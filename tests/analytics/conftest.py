from __future__ import annotations

import pytest

from simulator.harness import SimulationResult, run_scenario
from simulator.scenarios import REQUIRED_SCENARIO_NAMES, SCENARIO_BY_NAME


@pytest.fixture(scope="session")
def analytics_results(tmp_path_factory: pytest.TempPathFactory) -> dict[str, SimulationResult]:
    root = tmp_path_factory.mktemp("commit9-reports")
    return {
        name: run_scenario(SCENARIO_BY_NAME[name](), root / name, seed=42)
        for name in REQUIRED_SCENARIO_NAMES
    }


@pytest.fixture(scope="session")
def normal_report_result(
    analytics_results: dict[str, SimulationResult],
) -> SimulationResult:
    return analytics_results["normal-pace-loss"]


@pytest.fixture(scope="session")
def long_stop_result(
    analytics_results: dict[str, SimulationResult],
) -> SimulationResult:
    return analytics_results["long-stop-mid-length"]
