from __future__ import annotations

import json
from pathlib import Path

from simulator.harness import SimulationResult
from simulator.scenarios import SCENARIO_BY_NAME
from swimtools.build_session_report import main


def test_report_builder_cli(tmp_path: Path, normal_report_result: SimulationResult) -> None:
    scenario = SCENARIO_BY_NAME["normal-pace-loss"]()
    workout = tmp_path / "workout.json"
    profile = tmp_path / "profile.json"
    output = tmp_path / "report.json"
    workout.write_text(json.dumps(scenario.workout.model_dump(mode="json")), encoding="utf-8")
    profile.write_text(json.dumps(scenario.profile.model_dump(mode="json")), encoding="utf-8")
    rc = main(
        [
            "--journal",
            str(normal_report_result.journalPath),
            "--workout",
            str(workout),
            "--pace-profile",
            str(profile),
            "--output",
            str(output),
        ]
    )
    assert rc == 0
    assert output.exists()
