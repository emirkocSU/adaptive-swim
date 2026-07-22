"""Deterministic scenario runner CLI (Commit 8, corrected §2.2).

Thin front-end over the simulator harness — it owns no domain logic, only argument parsing
and reporting. No network, no wall-clock time, no global randomness.

    python -m swimtools.run_scenario --list
    python -m swimtools.run_scenario --scenario normal-pace-loss --seed 42 --output ./run
    python -m swimtools.run_scenario --scenario coach-continuous-curve-reset --output ./run

``--seed`` is fed to the REAL virtual-swimmer RNG (never merely reported); when omitted the
scenario registry's default seed is used. Same scenario + same seed → identical observation
trace, event stream and journal SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from simulator.harness import run_scenario
from simulator.scenarios import (
    REQUIRED_SCENARIO_NAMES,
    SCENARIO_BY_NAME,
    build_all_scenarios,
)


def _journal_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observation_digest(result: object) -> str:
    """SHA-256 over the per-tick observation trace (seed sensitivity is visible here)."""
    from simulator.harness import SimulationResult

    assert isinstance(result, SimulationResult)
    payload = "\n".join(
        f"{o.wallTimeMs},{o.activeTimeMs},{o.actualDistanceM},{o.actualSpeedMps},"
        f"{o.targetDistanceM},{o.targetSpeedMps},{o.gapM},{o.phaseType},"
        f"{o.positionQuality},{int(o.plannedRest)}"
        for o in result.observations
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run(name: str, seed: int | None, output: Path, fmt: str) -> int:
    builder = SCENARIO_BY_NAME.get(name)
    if builder is None:
        available = ", ".join(sorted(SCENARIO_BY_NAME))
        print(f"unknown scenario: {name}", file=sys.stderr)
        print(f"available: {available}", file=sys.stderr)
        return 2
    scenario = builder()
    output.mkdir(parents=True, exist_ok=True)
    result = run_scenario(scenario, output, seed=seed)
    st = result.replayResult.state

    report = {
        "scenario": result.scenarioId,
        "scenarioVersion": result.scenarioVersion,
        "seed": result.seed,
        "runId": result.runId,
        "required": result.scenarioId in REQUIRED_SCENARIO_NAMES,
        "eventCount": len(result.events),
        "batchCount": len(result.eventBatches),
        "observationCount": len(result.observations),
        "observationDigest": _observation_digest(result),
        "lifecycleState": st.lifecycleState.value,
        "activeDurationMs": st.activeDurationMs,
        "stoppedDurationMs": st.stoppedDurationMs,
        "elapsedDurationMs": st.elapsedDurationMs,
        "officialCompletedDistanceM": st.officialCompletedDistanceM,
        "journalPath": str(result.journalPath),
        "journalSha256": _journal_sha256(result.journalPath),
        "sessionReportPath": str(result.sessionReportPath),
        "sessionReportId": result.sessionReport.reportId,
        "sessionReportSha256": result.sessionReportSha256,
        "replayStatus": "OK" if result.replayMatchesLiveState else "MISMATCH",
        "continuousProfileId": st.selectedPaceProfileId,
        "continuousProfileVersion": st.selectedPaceProfileVersion,
        "profileSource": st.selectedPaceProfileSource,
        "profileCoachLocked": st.profileCoachLocked,
        "curveRepresentation": st.selectedCurveRepresentation,
        "curveCompilerVersion": st.selectedCurveCompilerVersion,
        "synthetic": result.manifest.synthetic,
    }

    if fmt == "json":
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for key in (
            "scenario",
            "scenarioVersion",
            "seed",
            "runId",
            "eventCount",
            "batchCount",
            "observationCount",
            "observationDigest",
            "lifecycleState",
            "activeDurationMs",
            "stoppedDurationMs",
            "elapsedDurationMs",
            "officialCompletedDistanceM",
            "journalPath",
            "journalSha256",
            "sessionReportPath",
            "sessionReportId",
            "sessionReportSha256",
            "replayStatus",
            "continuousProfileId",
            "continuousProfileVersion",
            "profileSource",
            "profileCoachLocked",
            "curveRepresentation",
            "curveCompilerVersion",
            "synthetic",
        ):
            print(f"{key}: {report[key]}")
    return 0 if result.replayMatchesLiveState else 1


def _list() -> int:
    for scenario in build_all_scenarios():
        tag = "required" if scenario.scenarioId in REQUIRED_SCENARIO_NAMES else "demo"
        print(
            f"{scenario.scenarioId}\t[{tag}]\tseed={scenario.defaultSeed}\t{scenario.description}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="swimtools.run_scenario",
        description="Adaptive Swim deterministic scenario runner",
    )
    parser.add_argument("--list", action="store_true", help="list available scenarios")
    parser.add_argument("--scenario", default=None, help="scenario slug")
    parser.add_argument(
        "--seed", type=int, default=None, help="seed fed to the real virtual-swimmer RNG"
    )
    parser.add_argument("--output", type=Path, default=None, help="output directory")
    parser.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)
    if args.list:
        return _list()
    if args.scenario is None or args.output is None:
        parser.error("--scenario and --output are required unless --list is given")
    return _run(args.scenario, args.seed, args.output, args.format)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
