"""Deterministic headless simulation harness (Commit 8).

Drives the **real** ``SessionAggregate`` through real commands and persists every emitted
event batch with the **real** ``JsonlSessionEventLog``. It embeds the production runtime; it
never re-implements pacing, ghost, session, persistence or replay logic. Every run is
deterministic (SimClock + seeded virtual swimmer) and records a provenance block so the
resulting journal can be published as an ``ADAPTIVE_SWIM_SESSION`` / ``SYNTHETIC_SIMULATION``
external-data record with full lineage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contracts.commands import (
    ArmSession,
    Command,
    CompleteSession,
    CreateSession,
    MarkStopPause,
    RecordSplit,
    ResolveStopPause,
    StartSession,
)
from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.enums import (
    AlignmentSource,
    SplitSource,
    StopDetectionSource,
    StopPauseTrigger,
)
from contracts.events import EventEnvelope
from contracts.pace_profiles import ApprovedPaceProfile
from contracts.workout import WorkoutTemplateV1_1
from persistence import JsonlSessionEventLog
from simulator.provenance import SimulationProvenance, build_provenance
from swimcore.pacing.profile_compiler import compile_live_profile
from swimcore.pacing.timeline import target_active_time_at_distance
from swimcore.session import SequenceIdGenerator, SessionAggregate
from swimcore.time import SimClock
from swimcore.workout.start_mode import resolve_repeat_start_mode

_SIM_HARNESS_VERSION = "sim-harness-1.0.0"


@dataclass(frozen=True, slots=True)
class ScenarioStop:
    """A StopPause the scenario injects after a given wall index."""

    afterLengthIndex: int
    durationMs: int
    trackedAlignmentDistanceM: float


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    """A fully specified deterministic scenario.

    ``profile`` is a live-eligible approved profile (1.0 or 1.1); ``workout`` its 1.1 host.
    The virtual swimmer's wall touches are provided directly (already deterministic) so the
    harness stays a thin driver. A single optional StopPause and an optional coach continuous
    reset may be injected.
    """

    name: str
    seed: int
    workout: WorkoutTemplateV1_1
    profile: ApprovedPaceProfile | ApprovedContinuousPaceProfile
    wallTouches: tuple[tuple[int, float, int], ...]  # (lengthIndex, distanceM, wallTsMs)
    stop: ScenarioStop | None = None
    replacementProfile: ApprovedContinuousPaceProfile | None = None
    replacementAfterLengthIndex: int | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class SimulationResult:
    scenarioName: str
    sessionId: str
    events: tuple[EventEnvelope, ...]
    journalPath: Path
    provenance: SimulationProvenance
    wallCount: int
    stopInjected: bool
    replacementInjected: bool
    extraFiles: tuple[Path, ...] = field(default=())


def ghost_wall_targets(
    profile: ApprovedPaceProfile | ApprovedContinuousPaceProfile,
    *,
    pool_length_m: int,
    resolved_start_mode: object,
    stroke: object,
    total_distance_m: float,
) -> list[int]:
    """Ghost active-time target (ms) at each official wall, from the real compiled timeline."""
    timeline = compile_live_profile(
        profile,
        pool_length_m=pool_length_m,
        resolved_start_mode=resolved_start_mode,
        stroke=stroke,
        total_distance_m=total_distance_m,
    )
    walls = int(round(total_distance_m / pool_length_m))
    targets: list[int] = []
    for k in range(1, walls + 1):
        d = min(float(k * pool_length_m), total_distance_m)
        sec = target_active_time_at_distance(timeline, d).elapsedActiveSec
        targets.append(int(round(sec * 1000.0)))
    return targets


def run_scenario(
    scenario: SimulationScenario,
    output_dir: Path,
    *,
    profile_ref: str = "p1",
    replacement_ref: str = "pRepl",
    workout_ref: str = "w1",
) -> SimulationResult:
    """Run one scenario deterministically and persist its journal. Pure of wall-clock time."""
    output_dir.mkdir(parents=True, exist_ok=True)
    clock = SimClock(0)
    id_gen = SequenceIdGenerator("sim")

    profiles: dict[str, ApprovedPaceProfile | ApprovedContinuousPaceProfile] = {
        profile_ref: scenario.profile
    }
    if scenario.replacementProfile is not None:
        profiles[replacement_ref] = scenario.replacementProfile

    agg = SessionAggregate(
        {},
        clock,
        id_gen,
        profiles=profiles,
        workouts_v1_1={workout_ref: scenario.workout},
    )

    all_events: list[EventEnvelope] = []
    log: JsonlSessionEventLog | None = None

    def drive(command: Command, at_ms: int) -> None:
        nonlocal log
        clock.set_to(at_ms)
        batch = agg.handle(command)
        if not batch:
            return
        if log is None:
            sid = batch[0].sessionId
            assert sid is not None
            log = JsonlSessionEventLog(output_dir / f"{scenario.name}.jsonl", sid)
        log.append_batch(batch)
        all_events.extend(batch)

    drive(
        CreateSession(clientCommandId="create", workoutRef=workout_ref, paceProfileRef=profile_ref),
        0,
    )
    sid = agg.sessionId
    assert sid is not None
    drive(ArmSession(clientCommandId="arm", sessionId=sid), 0)
    drive(StartSession(clientCommandId="start", sessionId=sid), 0)

    stop_injected = False
    replacement_injected = False
    for length_index, distance_m, wall_ts in scenario.wallTouches:
        # inject a StopPause immediately before this wall's split when scheduled
        if (
            scenario.stop is not None
            and scenario.stop.afterLengthIndex == length_index - 1
            and not stop_injected
        ):
            stop = scenario.stop
            stop_started = max(wall_ts - stop.durationMs, 1)
            drive(
                MarkStopPause(
                    clientCommandId=f"stop-{length_index}",
                    sessionId=sid,
                    trigger=StopPauseTrigger.MANUAL_INCIDENT,
                    stopStartedAtMs=stop_started,
                    confirmedAtMs=stop_started + 1,
                    detectionSource=StopDetectionSource.COACH,
                    alignmentSource=AlignmentSource.COACH_MARK,
                    trackedAlignmentDistanceM=stop.trackedAlignmentDistanceM,
                    createdBy="coach",
                ),
                stop_started + 1,
            )
            drive(
                ResolveStopPause(
                    clientCommandId=f"resolve-{length_index}",
                    sessionId=sid,
                    intervalId=f"{sid}-stop-1",
                    resumedAtMs=wall_ts,
                ),
                wall_ts,
            )
            stop_injected = True

        # optional coach continuous-curve reset request before the target wall
        if (
            scenario.replacementProfile is not None
            and scenario.replacementAfterLengthIndex == length_index - 1
            and not replacement_injected
        ):
            from contracts.commands import CoachPacingReset

            drive(
                CoachPacingReset(
                    clientCommandId=f"reset-{length_index}",
                    sessionId=sid,
                    reason="coach-continuous-reset",
                    replacementPaceProfileRef=replacement_ref,
                ),
                max(wall_ts - 1, 1),
            )
            replacement_injected = True

        drive(
            RecordSplit(
                clientCommandId=f"split-{length_index}",
                sessionId=sid,
                splitId=f"L{length_index}",
                lengthIndex=length_index,
                wallTimestampMs=wall_ts,
                source=SplitSource.SIMULATED,
                distanceM=distance_m,
            ),
            wall_ts,
        )

    last_ts = scenario.wallTouches[-1][2] if scenario.wallTouches else 0
    drive(CompleteSession(clientCommandId="complete", sessionId=sid), last_ts)

    assert log is not None
    provenance = build_provenance(
        scenario_name=scenario.name,
        seed=scenario.seed,
        session_id=sid,
        harness_version=_SIM_HARNESS_VERSION,
        profile=scenario.profile,
        replacement_profile=scenario.replacementProfile,
        event_count=len(all_events),
    )
    return SimulationResult(
        scenarioName=scenario.name,
        sessionId=sid,
        events=tuple(all_events),
        journalPath=log.path,
        provenance=provenance,
        wallCount=len(scenario.wallTouches),
        stopInjected=stop_injected,
        replacementInjected=replacement_injected,
    )


def resolve_start_mode_for(workout: WorkoutTemplateV1_1) -> object:
    """Resolve the workout's first-repeat start mode (used to build ghost targets)."""
    return resolve_repeat_start_mode(workout, 0, 0)
