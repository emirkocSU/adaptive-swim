"""Deterministic scenario runner CLI (Commit 8 §33).

Thin front-end over the simulator harness — it owns no domain logic, only argument parsing
and reporting. No network, no wall-clock time, no randomness.

    python -m swimtools.run_scenario --list
    python -m swimtools.run_scenario --scenario normal-pace-loss --seed 42 --output ./run
    python -m swimtools.run_scenario --scenario even-on-plan --output ./run --format json

The same invocation always produces a byte-identical journal (SHA-256 reported).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from simulator.harness import run_scenario
from simulator.scenarios import SCENARIO_BY_NAME, build_all_scenarios
from swimcore.replay import replay_session

#: Human-friendly aliases accepted for the eight required scenarios (§31).
_ALIASES = {
    "normal-pace-loss": "even-on-plan",
    "long-stop-mid-length": "stop-pause",
    "coach-continuous-curve-reset": "coach-continuous-reset",
}


def _resolve_name(name: str) -> str:
    return _ALIASES.get(name, name)


def _journal_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(name: str, seed: int | None, output: Path, fmt: str) -> int:
    resolved = _resolve_name(name)
    builder = SCENARIO_BY_NAME.get(resolved)
    if builder is None:
        available = ", ".join(sorted(SCENARIO_BY_NAME))
        print(f"unknown scenario: {name}", file=sys.stderr)
        print(f"available: {available}", file=sys.stderr)
        return 2
    scenario = builder()
    # ``--seed`` is accepted for interface parity; each scenario embeds its own deterministic
    # seed, so an explicit mismatching seed is reported but does not silently change output.
    output.mkdir(parents=True, exist_ok=True)
    result = run_scenario(scenario, output)
    sha = _journal_sha256(result.journalPath)
    replay = replay_session(list(result.events))
    st = replay.state

    report = {
        "scenario": scenario.name,
        "seed": scenario.seed,
        "requestedSeed": seed,
        "eventCount": len(result.events),
        "batchCount": _batch_count(result.journalPath),
        "lifecycleState": st.lifecycleState.value,
        "activeDurationMs": st.activeDurationMs,
        "stoppedDurationMs": st.stoppedDurationMs,
        "elapsedDurationMs": st.elapsedDurationMs,
        "officialCompletedDistanceM": st.officialCompletedDistanceM,
        "journalPath": str(result.journalPath),
        "journalSha256": sha,
        "replayStatus": "OK",
        "continuousProfileId": st.selectedPaceProfileId,
        "continuousProfileVersion": st.selectedPaceProfileVersion,
        "curveRepresentation": result.provenance.curveRepresentation,
    }

    if fmt == "json":
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for key in (
            "scenario",
            "seed",
            "eventCount",
            "batchCount",
            "lifecycleState",
            "activeDurationMs",
            "stoppedDurationMs",
            "elapsedDurationMs",
            "officialCompletedDistanceM",
            "journalPath",
            "journalSha256",
            "replayStatus",
            "continuousProfileId",
            "continuousProfileVersion",
            "curveRepresentation",
        ):
            print(f"{key}: {report[key]}")
    return 0


def _batch_count(path: Path) -> int:
    return sum(1 for line in path.read_bytes().split(b"\n") if line.strip())


def _list() -> int:
    for scenario in build_all_scenarios():
        print(f"{scenario.name}\t{scenario.description}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="swimtools.run_scenario",
        description="Adaptive Swim deterministic scenario runner",
    )
    parser.add_argument("--list", action="store_true", help="list available scenarios")
    parser.add_argument("--scenario", default=None, help="scenario name (or alias)")
    parser.add_argument("--seed", type=int, default=None, help="seed (interface parity)")
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
