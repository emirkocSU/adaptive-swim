"""Shared file parsing for report CLIs; contains no analytics/domain decisions."""

from __future__ import annotations

import json
from pathlib import Path

from analytics.types import (
    ApprovedPaceProfileVersion,
    SensorObservation,
    SessionObservation,
)
from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.events import EventEnvelope
from contracts.pace_profiles import ApprovedPaceProfile
from contracts.workout import AnyWorkoutTemplate, WorkoutTemplateV1_1, WorkoutTemplateVersion
from persistence.codec import decode_batch
from persistence.jsonl_event_log import JsonlSessionEventLog
from swimcore.pacing.profile_compiler import compile_live_profile
from swimcore.pacing.types import PaceTimeline
from swimcore.workout.start_mode import resolve_repeat_start_mode


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_workout(path: Path) -> AnyWorkoutTemplate:
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("workout JSON must be an object")
    if raw.get("schemaVersion") == "1.1":
        return WorkoutTemplateV1_1.model_validate(raw)
    return WorkoutTemplateVersion.model_validate(raw)


def read_profile(path: Path) -> ApprovedPaceProfileVersion:
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("pace-profile JSON must be an object")
    if raw.get("schemaVersion") == "1.1":
        return ApprovedContinuousPaceProfile.model_validate(raw)
    return ApprovedPaceProfile.model_validate(raw)


def read_journal(path: Path) -> tuple[EventEnvelope, ...]:
    with path.open("rb") as handle:
        first = handle.readline()
    if not first:
        raise ValueError("journal is empty")
    first_batch = decode_batch(first)
    return JsonlSessionEventLog(path, first_batch.sessionId).read_all().events


def compile_profile(
    workout: AnyWorkoutTemplate, profile: ApprovedPaceProfileVersion
) -> PaceTimeline:
    if isinstance(workout, WorkoutTemplateV1_1):
        start_mode = resolve_repeat_start_mode(workout, 0, 0)
    else:
        start_mode = profile.startMode
    return compile_live_profile(
        profile,
        pool_length_m=workout.poolLengthM,
        resolved_start_mode=start_mode,
        stroke=workout.stroke,
        total_distance_m=profile.totalDistanceM,
    )


def read_observations(path: Path | None) -> tuple[SessionObservation, ...]:
    if path is None:
        return ()
    raw = read_json(path)
    if not isinstance(raw, list):
        raise ValueError("observations JSON must be an array")
    return tuple(SessionObservation(**item) for item in raw if isinstance(item, dict))


def read_sensor_observations(path: Path | None) -> tuple[SensorObservation, ...]:
    if path is None:
        return ()
    raw = read_json(path)
    if not isinstance(raw, list):
        raise ValueError("sensor observations JSON must be an array")
    return tuple(SensorObservation(**item) for item in raw if isinstance(item, dict))
