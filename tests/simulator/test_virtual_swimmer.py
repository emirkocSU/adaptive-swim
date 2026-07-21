"""VirtualSwimmer, provenance and CLI unit tests (Commit 8 §38)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from simulator.scenarios import build_all_scenarios
from simulator.virtual_swimmer import (
    SwimmerBehaviour,
    _SplitMix64,
    swim_walls,
)

pytestmark = pytest.mark.simulator


def test_prng_is_deterministic() -> None:
    a = _SplitMix64(42)
    b = _SplitMix64(42)
    assert [a.next_u64() for _ in range(5)] == [b.next_u64() for _ in range(5)]


def test_prng_differs_by_seed() -> None:
    a = [_SplitMix64(1).next_u64() for _ in range(5)]
    b = [_SplitMix64(2).next_u64() for _ in range(5)]
    assert a != b


def test_swim_walls_on_plan() -> None:
    targets = [20_000, 40_000, 60_000, 80_000]
    touches = swim_walls(
        pool_length_m=25,
        total_distance_m=100.0,
        target_time_at_wall_ms=targets,
        behaviour=SwimmerBehaviour(),  # exactly on plan
        seed=1,
    )
    assert [t.distanceM for t in touches] == [25.0, 50.0, 75.0, 100.0]
    assert [t.wallTimestampMs for t in touches] == targets


def test_swim_walls_deterministic_with_jitter() -> None:
    targets = [20_000, 40_000, 60_000, 80_000]
    behaviour = SwimmerBehaviour(paceBiasFactor=1.05, jitterFractionPerLength=0.05)
    a = swim_walls(
        pool_length_m=25,
        total_distance_m=100.0,
        target_time_at_wall_ms=targets,
        behaviour=behaviour,
        seed=7,
    )
    b = swim_walls(
        pool_length_m=25,
        total_distance_m=100.0,
        target_time_at_wall_ms=targets,
        behaviour=behaviour,
        seed=7,
    )
    assert a == b


def test_swim_walls_bias_slows_swimmer() -> None:
    targets = [20_000, 40_000]
    on_plan = swim_walls(
        pool_length_m=25,
        total_distance_m=50.0,
        target_time_at_wall_ms=targets,
        behaviour=SwimmerBehaviour(),
        seed=1,
    )
    slow = swim_walls(
        pool_length_m=25,
        total_distance_m=50.0,
        target_time_at_wall_ms=targets,
        behaviour=SwimmerBehaviour(paceBiasFactor=1.2),
        seed=1,
    )
    assert slow[-1].wallTimestampMs > on_plan[-1].wallTimestampMs


def test_all_scenarios_have_unique_seeds() -> None:
    scenarios = build_all_scenarios()
    seeds = [s.seed for s in scenarios]
    assert len(seeds) == len(set(seeds))
    assert len(scenarios) == 8


def test_provenance_run_id_style() -> None:
    from simulator.harness import run_scenario
    from simulator.scenarios import SCENARIO_BY_NAME

    with tempfile.TemporaryDirectory() as d:
        result = run_scenario(SCENARIO_BY_NAME["even-on-plan"](), Path(d))
        as_dict = result.provenance.as_dict()
        assert as_dict["usedRealHumanData"] is False
        assert as_dict["domain"] == "SYNTHETIC_SIMULATION"
        assert as_dict["seed"] == 1001


def test_cli_list(capsys: pytest.CaptureFixture[str]) -> None:
    from swimtools.run_scenario import main

    rc = main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "even-on-plan" in out


def test_cli_run_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from swimtools.run_scenario import main

    rc = main(
        [
            "--scenario",
            "even-on-plan",
            "--seed",
            "42",
            "--output",
            str(tmp_path),
            "--format",
            "json",
        ]
    )
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["scenario"] == "even-on-plan"
    assert report["lifecycleState"] == "COMPLETED"
    assert report["replayStatus"] == "OK"
    assert len(report["journalSha256"]) == 64


def test_cli_run_alias(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from swimtools.run_scenario import main

    rc = main(["--scenario", "long-stop-mid-length", "--output", str(tmp_path), "--format", "json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["scenario"] == "stop-pause"  # alias resolves


def test_cli_unknown_scenario(tmp_path: Path) -> None:
    from swimtools.run_scenario import main

    rc = main(["--scenario", "does-not-exist", "--output", str(tmp_path)])
    assert rc == 2


def test_cli_deterministic_hash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from swimtools.run_scenario import main

    main(["--scenario", "even-on-plan", "--output", str(tmp_path / "a"), "--format", "json"])
    a = json.loads(capsys.readouterr().out)["journalSha256"]
    main(["--scenario", "even-on-plan", "--output", str(tmp_path / "b"), "--format", "json"])
    b = json.loads(capsys.readouterr().out)["journalSha256"]
    assert a == b
