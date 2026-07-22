"""VirtualSwimmer, provenance and CLI unit tests (Commit 8, corrected §15)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from simulator.provenance import deterministic_run_id
from simulator.scenarios import REQUIRED_SCENARIO_NAMES, build_all_scenarios
from simulator.virtual_swimmer import (
    RestWindow,
    StopWindow,
    SwimmerBehaviour,
    VirtualSwimmerConfig,
    _SplitMix64,
    simulate_swim,
    swim_walls,
)

pytestmark = pytest.mark.simulator


# --------------------------------------------------------------------------- PRNG
def test_prng_is_deterministic() -> None:
    a = _SplitMix64(42)
    b = _SplitMix64(42)
    assert [a.next_u64() for _ in range(5)] == [b.next_u64() for _ in range(5)]


def test_prng_differs_by_seed() -> None:
    a = [_SplitMix64(1).next_u64() for _ in range(5)]
    b = [_SplitMix64(2).next_u64() for _ in range(5)]
    assert a != b


def test_gaussian_is_deterministic_and_seed_sensitive() -> None:
    a = [_SplitMix64(3).gauss(0.0, 0.1) for _ in range(4)]
    b = [_SplitMix64(3).gauss(0.0, 0.1) for _ in range(4)]
    c = [_SplitMix64(4).gauss(0.0, 0.1) for _ in range(4)]
    assert a == b
    assert a != c


# --------------------------------------------------------------------------- tick simulation
def _linear_plan(total_m: float, speed: float):  # noqa: ANN202
    def target_distance_at_active_ms(active_ms: int) -> float:
        return min(active_ms / 1000.0 * speed, total_m)

    def target_speed_at_distance(_d: float) -> float:
        return speed

    def phase_type_at_distance(_d: float) -> str:
        return "SURFACE_SWIM"

    return target_distance_at_active_ms, target_speed_at_distance, phase_type_at_distance


def _simulate(**overrides):  # noqa: ANN202, ANN003
    dist, speed_at, phase = _linear_plan(100.0, 1.25)
    kwargs = {
        "config": VirtualSwimmerConfig(seed=42, noiseStdMps=0.01),
        "pool_length_m": 25,
        "total_distance_m": 100.0,
        "target_distance_at_active_ms": dist,
        "target_speed_at_distance": speed_at,
        "phase_type_at_distance": phase,
    }
    kwargs.update(overrides)
    return simulate_swim(**kwargs)


def test_tick_simulation_emits_per_tick_observations() -> None:
    result = _simulate()
    assert len(result.observations) > 100
    assert len(result.wallTouches) == 4
    assert [t.distanceM for t in result.wallTouches] == [25.0, 50.0, 75.0, 100.0]
    first = result.observations[0]
    assert first.wallTimeMs == 0
    assert first.positionQuality == "HIGH"
    assert first.plannedRest is False


def test_tick_simulation_is_deterministic_for_a_seed() -> None:
    a = _simulate()
    b = _simulate()
    assert a.observations == b.observations
    assert a.wallTouches == b.wallTouches


def test_tick_simulation_differs_by_seed() -> None:
    a = _simulate(config=VirtualSwimmerConfig(seed=42, noiseStdMps=0.02))
    b = _simulate(config=VirtualSwimmerConfig(seed=99, noiseStdMps=0.02))
    assert [o.actualSpeedMps for o in a.observations] != [o.actualSpeedMps for o in b.observations]


def test_response_ratio_below_one_falls_behind() -> None:
    fast = _simulate(config=VirtualSwimmerConfig(seed=1, baseResponseRatio=1.0))
    slow = _simulate(config=VirtualSwimmerConfig(seed=1, baseResponseRatio=0.85))
    assert slow.wallTouches[-1].wallTimestampMs > fast.wallTouches[-1].wallTimestampMs
    assert max(o.gapM for o in slow.observations) > 3.0


def test_wall_crossing_is_interpolated_not_snapped_to_a_tick() -> None:
    # a plan whose length duration is not a whole number of ticks must produce at least one
    # wall timestamp off the tick grid (deterministic interpolation inside the tick)
    dist, speed_at, phase = _linear_plan(100.0, 1.2345)
    result = simulate_swim(
        config=VirtualSwimmerConfig(seed=5, tickMs=100, noiseStdMps=0.0),
        pool_length_m=25,
        total_distance_m=100.0,
        target_distance_at_active_ms=dist,
        target_speed_at_distance=speed_at,
        phase_type_at_distance=phase,
    )
    assert any(t.wallTimestampMs % 100 != 0 for t in result.wallTouches)


def test_planned_rest_zeroes_speed_without_any_stop_concept() -> None:
    result = _simulate(rest=RestWindow(afterLengthIndex=1, durationMs=5_000))
    rest_ticks = [o for o in result.observations if o.plannedRest]
    assert len(rest_ticks) >= 40
    assert all(o.actualSpeedMps == 0.0 for o in rest_ticks)
    assert result.restRealized is not None


def test_stop_window_is_reported_with_real_boundaries() -> None:
    result = _simulate(
        stop=StopWindow(afterLengthIndex=1, offsetAfterWallMs=2_000, durationMs=8_000)
    )
    assert result.stopRealized is not None
    start, end = result.stopRealized
    assert end - start == 8_000


def test_fatigue_slows_the_swimmer_over_distance() -> None:
    fresh = _simulate(config=VirtualSwimmerConfig(seed=2, fatigueSlopePer100M=0.0))
    tired = _simulate(config=VirtualSwimmerConfig(seed=2, fatigueSlopePer100M=0.10))
    assert tired.wallTouches[-1].wallTimestampMs > fresh.wallTouches[-1].wallTimestampMs


def test_turn_delay_adds_dwell_at_walls() -> None:
    quick = _simulate(config=VirtualSwimmerConfig(seed=2, turnDelayMs=0))
    slow = _simulate(config=VirtualSwimmerConfig(seed=2, turnDelayMs=500))
    assert slow.wallTouches[-1].wallTimestampMs > quick.wallTouches[-1].wallTimestampMs


# --------------------------------------------------------------------------- legacy model
def test_legacy_swim_walls_still_deterministic() -> None:
    targets = [20_000, 40_000, 60_000, 80_000]
    a = swim_walls(
        pool_length_m=25,
        total_distance_m=100.0,
        target_time_at_wall_ms=targets,
        behaviour=SwimmerBehaviour(paceBiasFactor=1.05, jitterFractionPerLength=0.05),
        seed=7,
    )
    b = swim_walls(
        pool_length_m=25,
        total_distance_m=100.0,
        target_time_at_wall_ms=targets,
        behaviour=SwimmerBehaviour(paceBiasFactor=1.05, jitterFractionPerLength=0.05),
        seed=7,
    )
    assert a == b


# --------------------------------------------------------------------------- registry / manifest
def test_required_scenarios_share_the_documented_default_seed() -> None:
    scenarios = {s.scenarioId: s for s in build_all_scenarios()}
    assert len(scenarios) == 14
    for name in REQUIRED_SCENARIO_NAMES:
        assert scenarios[name].defaultSeed == 42


def test_run_id_is_a_pure_function_of_identity() -> None:
    args = {
        "scenario_id": "normal-pace-loss",
        "scenario_version": "2.0.0",
        "scenario_digest": "a" * 64,
        "seed": 42,
        "workout_ref": "w1",
        "workout_digest": "b" * 64,
        "profile_digests": {"normal100:1": "c" * 64},
        "selected_profile_id": "normal100",
        "selected_profile_version": "1",
        "replacement_profile_id": None,
        "replacement_profile_version": None,
        "analytics_policy_digest": "d" * 64,
        "harness_version": "sim-harness-2.1.0",
    }
    assert deterministic_run_id(**args) == deterministic_run_id(**args)
    assert len(deterministic_run_id(**args)) == 64
    assert deterministic_run_id(**{**args, "seed": 43}) != deterministic_run_id(**args)
    changed_policy = {**args, "analytics_policy_digest": "e" * 64}
    changed_replacement = {
        **args,
        "profile_digests": {
            "normal100:1": "c" * 64,
            "replacement100:1": "e" * 64,
        },
        "replacement_profile_id": "replacement100",
        "replacement_profile_version": "1",
    }
    assert deterministic_run_id(**changed_policy) != deterministic_run_id(**args)
    assert deterministic_run_id(**changed_replacement) != deterministic_run_id(**args)


def test_manifest_marks_every_run_synthetic() -> None:
    from simulator.harness import run_scenario
    from simulator.scenarios import SCENARIO_BY_NAME

    with tempfile.TemporaryDirectory() as d:
        result = run_scenario(SCENARIO_BY_NAME["normal-pace-loss"](), Path(d))
        as_dict = result.manifest.as_dict()
        assert as_dict["synthetic"] is True
        assert as_dict["seed"] == 42
        assert as_dict["scenarioId"] == "normal-pace-loss"
        assert result.provenance.as_dict()["usedRealHumanData"] is False


# --------------------------------------------------------------------------- CLI
def test_cli_list_shows_all_eight_required(capsys: pytest.CaptureFixture[str]) -> None:
    from swimtools.run_scenario import main

    rc = main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    for name in REQUIRED_SCENARIO_NAMES:
        assert name in out


def test_cli_run_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from swimtools.run_scenario import main

    rc = main(
        [
            "--scenario",
            "normal-pace-loss",
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
    assert report["scenario"] == "normal-pace-loss"
    assert report["seed"] == 42
    assert report["lifecycleState"] == "COMPLETED"
    assert report["replayStatus"] == "OK"
    assert len(report["journalSha256"]) == 64
    assert report["synthetic"] is True


def test_cli_seed_changes_the_real_simulation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from swimtools.run_scenario import main

    main(
        [
            "--scenario",
            "normal-pace-loss",
            "--seed",
            "42",
            "--output",
            str(tmp_path / "a"),
            "--format",
            "json",
        ]
    )
    a = json.loads(capsys.readouterr().out)
    main(
        [
            "--scenario",
            "normal-pace-loss",
            "--seed",
            "42",
            "--output",
            str(tmp_path / "b"),
            "--format",
            "json",
        ]
    )
    b = json.loads(capsys.readouterr().out)
    main(
        [
            "--scenario",
            "normal-pace-loss",
            "--seed",
            "99",
            "--output",
            str(tmp_path / "c"),
            "--format",
            "json",
        ]
    )
    c = json.loads(capsys.readouterr().out)
    assert a["journalSha256"] == b["journalSha256"]
    assert a["observationDigest"] == b["observationDigest"]
    assert a["observationDigest"] != c["observationDigest"]


def test_cli_rejects_removed_aliases(tmp_path: Path) -> None:
    """The old alias names must NOT resolve to a required slug any more."""
    from swimtools.run_scenario import main

    rc = main(["--scenario", "stop-pause", "--output", str(tmp_path)])
    assert rc == 2


def test_cli_unknown_scenario(tmp_path: Path) -> None:
    from swimtools.run_scenario import main

    rc = main(["--scenario", "does-not-exist", "--output", str(tmp_path)])
    assert rc == 2
