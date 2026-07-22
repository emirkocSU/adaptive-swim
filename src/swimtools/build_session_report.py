"""Offline deterministic SessionReport 1.1 builder CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from analytics import (
    ProfileRuntimeContext,
    ReportBuildContext,
    build_session_report,
    encode_session_report,
)
from swimcore.replay.reducer import replay_session
from swimtools._report_io import (
    compile_profile,
    read_journal,
    read_observations,
    read_profile,
    read_sensor_observations,
    read_workout,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swimtools.build_session_report")
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--workout", type=Path, required=True)
    parser.add_argument("--pace-profile", type=Path, required=True)
    parser.add_argument(
        "--replacement-pace-profile",
        dest="replacement_profiles",
        type=Path,
        action="append",
        default=[],
        help="replacement profile JSON used by an applied coach reset; repeatable",
    )
    parser.add_argument(
        "--profile-registry",
        type=Path,
        help="directory containing replacement profile JSON files",
    )
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--sensor-observations", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("json",), default="json")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        events = read_journal(args.journal)
        workout = read_workout(args.workout)
        profile = read_profile(args.pace_profile)
        timeline = compile_profile(workout, profile)
        registry_paths: list[Path] = list(args.replacement_profiles)
        if args.profile_registry is not None:
            if not args.profile_registry.is_dir():
                raise ValueError("--profile-registry must be a directory")
            registry_paths.extend(sorted(args.profile_registry.glob("*.json")))
        profile_registry: dict[tuple[str, str], ProfileRuntimeContext] = {}
        for path in registry_paths:
            replacement = read_profile(path)
            key = (replacement.profileId, replacement.profileVersion)
            if key in profile_registry:
                raise ValueError(f"duplicate replacement profile {key[0]}:{key[1]}")
            profile_registry[key] = ProfileRuntimeContext(
                profile=replacement,
                timeline=compile_profile(workout, replacement),
            )
        replay = replay_session(events)
        report = build_session_report(
            replay_state=replay.state,
            events=events,
            workout=workout,
            pace_profile=profile,
            compiled_timeline=timeline,
            observations=read_observations(args.observations),
            sensor_samples=read_sensor_observations(args.sensor_observations),
            report_context=ReportBuildContext(profileRegistry=profile_registry),
        )
        canonical = encode_session_report(report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical)
        if args.pretty:
            print(
                json.dumps(
                    report.model_dump(mode="json", exclude_none=False),
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
            )
        else:
            print(f"wrote {args.output} reportId={report.reportId}")
        return 0
    except Exception as exc:  # typed domain/codec validation is rendered as one CLI error
        print(f"report build failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
