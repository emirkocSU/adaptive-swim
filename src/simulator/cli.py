"""Headless simulator CLI (Commit 8).

Runs one or all deterministic scenarios, persists each journal with the real event log, and
writes a per-run provenance JSON. No wall-clock time, randomness, or network is used; a
given invocation always produces byte-identical output.

    python -m simulator run --out <dir> [--scenario <name>]
    python -m simulator list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from simulator.harness import SimulationResult, run_scenario
from simulator.scenarios import SCENARIO_BY_NAME, build_all_scenarios


def _write_provenance(result: SimulationResult, out_dir: Path) -> Path:
    path = out_dir / f"{result.scenarioName}.provenance.json"
    path.write_text(
        json.dumps(result.provenance.as_dict(), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return path


def _run(scenario_name: str | None, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    if scenario_name is not None:
        builder = SCENARIO_BY_NAME.get(scenario_name)
        if builder is None:
            print(f"unknown scenario: {scenario_name}", file=sys.stderr)
            print(f"available: {', '.join(sorted(SCENARIO_BY_NAME))}", file=sys.stderr)
            return 2
        scenarios = [builder()]
    else:
        scenarios = build_all_scenarios()

    for scenario in scenarios:
        result = run_scenario(scenario, out_dir)
        prov_path = _write_provenance(result, out_dir)
        print(
            f"{result.scenarioName}: {result.wallCount} walls, "
            f"{len(result.events)} events -> {result.journalPath.name}, {prov_path.name}"
        )
    return 0


def _list() -> int:
    for scenario in build_all_scenarios():
        print(f"{scenario.name}\t{scenario.description}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="simulator", description="Adaptive Swim headless simulator"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run one or all scenarios")
    run_p.add_argument("--out", required=True, type=Path, help="output directory for journals")
    run_p.add_argument("--scenario", default=None, help="scenario name (default: all)")

    sub.add_parser("list", help="list available scenarios")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args.scenario, args.out)
    if args.command == "list":
        return _list()
    parser.print_help(sys.stderr)  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
