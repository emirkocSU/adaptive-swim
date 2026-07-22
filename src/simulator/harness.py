"""Deterministic headless simulation harness (Commit 8, corrected).

Drives the **real** ``SessionAggregate`` through real commands and persists every emitted
event batch with the **real** ``JsonlSessionEventLog``. It embeds the production runtime
and never re-implements pacing, ghost, session, persistence or replay logic.

Acceptance-level guarantees built into the harness itself (§2.4):

- the run re-reads its own journal, flattens the events, calls the pure
  ``replay_session`` and verifies that every comparable field of the live aggregate state
  matches the historical replay state — a mismatch FAILS the simulation;
- the journal SHA-256 is computed and returned;
- the :class:`SimulationResult` carries scenario identity, seed, deterministic run
  manifest, every command with its outcome, all events and event batches, the full
  per-tick observation trace, ghost snapshots, the live final state and the replay result.

Determinism: SimClock + an instance-locally seeded virtual swimmer; the same
(scenario, seed) always yields a byte-identical journal.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path

from analytics import (
    ProfileRuntimeContext,
    ReportBuildContext,
    SessionObservation,
    build_session_report,
    encode_session_report,
)
from analytics.identity import canonical_digest_sha256, report_policy_digest_sha256
from contracts.commands import (
    ArmSession,
    CoachPacingReset,
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
    AlignmentQuality,
    AlignmentSource,
    SplitSource,
    StopDetectionSource,
    StopPauseTrigger,
    StopSignalQuality,
    StopStartTimeQuality,
    Stroke,
)
from contracts.events import EventEnvelope
from contracts.pace_profiles import ApprovedPaceProfile
from contracts.session_report import SessionReportV1_1
from contracts.workout import WorkoutTemplateV1_1
from persistence import JsonlSessionEventLog
from simulator.provenance import (
    SimulationProvenance,
    SimulationRunManifest,
    build_provenance,
    build_run_manifest,
)
from simulator.virtual_swimmer import (
    RestWindow,
    StopWindow,
    SwimmerObservation,
    UnreliableWindow,
    VirtualSwimmerConfig,
    simulate_swim,
)
from swimcore.pacing.profile_compiler import compile_live_profile
from swimcore.pacing.timeline import (
    ghost_distance_at_active_time,
    target_active_time_at_distance,
    target_speed_at_distance,
)
from swimcore.pacing.types import PaceTimeline
from swimcore.replay import ReplayResult, replay_session
from swimcore.session import SequenceIdGenerator, SessionAggregate
from swimcore.session.errors import SessionError
from swimcore.session.state import SessionState
from swimcore.time import SimClock
from swimcore.workout.start_mode import resolve_repeat_start_mode

_SIM_HARNESS_VERSION = "sim-harness-2.1.0"


class SimulationError(Exception):
    """A simulation run violated one of its acceptance guarantees."""


# --------------------------------------------------------------------------- scenario spec
@dataclass(frozen=True, slots=True)
class ScenarioStop:
    """A StopPause the scenario injects, anchored after a given wall index.

    ``offsetAfterWallMs = 0`` models a manual stop AT the verified wall (alignment from
    the official wall, no mid-pool estimate); a positive offset stops mid-length.
    ``confirmDelayMs`` separates the real (retroactive) stop start from the confirmation.
    """

    afterLengthIndex: int
    offsetAfterWallMs: int
    durationMs: int
    trackedAlignmentDistanceM: float
    trigger: StopPauseTrigger = StopPauseTrigger.MANUAL_INCIDENT
    detectionSource: StopDetectionSource = StopDetectionSource.COACH
    alignmentSource: AlignmentSource = AlignmentSource.TRACKED_POSITION
    alignmentQuality: AlignmentQuality = AlignmentQuality.HIGH
    detectionQuality: StopSignalQuality = StopSignalQuality.HIGH
    stopStartTimeQuality: StopStartTimeQuality = StopStartTimeQuality.HIGH
    confirmDelayMs: int = 1
    #: re-send the identical MarkStopPause (same clientCommandId + content) once more.
    duplicateMark: bool = False
    #: The stop happens AT the wall ``afterLengthIndex``: the mark/resolve are driven
    #: BEFORE that wall's split, whose official touch is registered on resume. The
    #: alignment is the official wall itself, so the single reconciliation lands on it.
    atWallBeforeSplit: bool = False


@dataclass(frozen=True, slots=True)
class SwimmerParams:
    """Scenario-level swimmer behaviour (seed comes from the run, not the scenario)."""

    baseResponseRatio: float = 1.0
    fatigueSlopePer100M: float = 0.0
    noiseStdMps: float = 0.0
    turnDelayMs: int = 0
    tickMs: int = 100
    minimumActualSpeedMps: float = 0.05
    maximumActualSpeedMps: float = 3.5


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    """A fully specified deterministic scenario (Commit 8, corrected)."""

    scenarioId: str
    scenarioVersion: str
    defaultSeed: int
    workout: WorkoutTemplateV1_1
    profile: ApprovedPaceProfile | ApprovedContinuousPaceProfile
    swimmer: SwimmerParams = field(default_factory=SwimmerParams)
    stop: ScenarioStop | None = None
    rest: RestWindow | None = None
    unreliable: UnreliableWindow | None = None
    #: attempt CompleteSession while the StopPause is still open (must be rejected).
    attemptCompleteWhileStopPaused: bool = False
    replacementProfile: ApprovedContinuousPaceProfile | None = None
    #: coach continuous-curve reset REQUESTED mid-length after this wall index.
    replacementAfterLengthIndex: int | None = None
    description: str = ""

    @property
    def name(self) -> str:
        return self.scenarioId


# --------------------------------------------------------------------------- result
@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """What happened to one driven command (§2.4)."""

    clientCommandId: str
    commandType: str
    atMs: int
    outcome: str  # APPLIED | IDEMPOTENT_REPLAY | REJECTED
    eventCount: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class GhostSnapshot:
    """Ghost target state sampled at one official wall."""

    lengthIndex: int
    wallTimestampMs: int
    ghostTargetActiveMsAtWall: int
    swimmerGapMsAtWall: int


@dataclass(frozen=True, slots=True)
class LiveFinalState:
    """Comparable snapshot of the live aggregate at the end of the run."""

    sessionId: str
    lifecycleState: str
    recordedSplitCount: int
    officialCompletedDistanceM: float
    selectedPaceProfileId: str | None
    selectedPaceProfileVersion: str | None
    selectedPaceProfileSource: str | None
    selectedPaceProfileType: str | None
    profileCoachLocked: bool
    selectedProfileTargetTotalTimeSec: float | None
    selectedCurveRepresentation: str | None
    selectedCurveCompilerVersion: str | None
    appliedPaceSecPer100M: float | None
    openStopPause: bool
    pendingCoachPacingReset: bool
    #: Live ActiveClock totals at the report horizon, so an external verifier can compare
    #: them against the independently replayed timing axes.
    activeDurationMs: int | None = None
    stoppedDurationMs: int | None = None
    wallElapsedMs: int | None = None


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Complete deterministic result of one scenario run (§2.4)."""

    scenarioId: str
    scenarioVersion: str
    seed: int
    runId: str
    manifest: SimulationRunManifest
    sessionId: str
    commands: tuple[Command, ...]
    commandOutcomes: tuple[CommandOutcome, ...]
    events: tuple[EventEnvelope, ...]
    eventBatches: tuple[tuple[EventEnvelope, ...], ...]
    observations: tuple[SwimmerObservation, ...]
    ghostSnapshots: tuple[GhostSnapshot, ...]
    journalPath: Path
    journalSha256: str
    liveFinalState: LiveFinalState
    replayResult: ReplayResult
    replayMatchesLiveState: bool
    provenance: SimulationProvenance
    wallCount: int
    stopInjected: bool
    replacementInjected: bool
    completeRejectedWhileStopPaused: bool
    sessionReport: SessionReportV1_1
    #: Observations handed to analytics, exposed so an external verifier can rebuild the
    #: identical report from the journal without duplicating the mapping.
    analyticsObservations: tuple[SessionObservation, ...]
    sessionReportBytes: bytes
    sessionReportSha256: str
    sessionReportPath: Path


# --------------------------------------------------------------------------- helpers
def resolve_start_mode_for(workout: WorkoutTemplateV1_1) -> object:
    """Resolve the workout's first-repeat start mode (used to build ghost targets)."""
    return resolve_repeat_start_mode(workout, 0, 0)


def compile_ghost_timeline(
    profile: ApprovedPaceProfile | ApprovedContinuousPaceProfile,
    workout: WorkoutTemplateV1_1,
) -> PaceTimeline:
    """Compile the REAL production ghost timeline for a scenario plan."""
    resolved = resolve_start_mode_for(workout)
    total = float(workout.blocks[0].distanceM)
    return compile_live_profile(
        profile,
        pool_length_m=workout.poolLengthM,
        resolved_start_mode=resolved,
        stroke=Stroke(workout.stroke),
        total_distance_m=total,
    )


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


def _phase_lookup(
    profile: ApprovedPaceProfile | ApprovedContinuousPaceProfile,
) -> list[tuple[float, float, str]]:
    if isinstance(profile, ApprovedContinuousPaceProfile):
        return [(p.fromM, p.toM, p.phaseType.value) for p in profile.phases]
    return [(leg.fromM, leg.toM, leg.phaseType.value) for leg in profile.legs]


# --------------------------------------------------------------------------- runner
def run_scenario(
    scenario: SimulationScenario,
    output_dir: Path,
    *,
    seed: int | None = None,
    profile_ref: str = "p1",
    replacement_ref: str = "pRepl",
    workout_ref: str = "w1",
    report_context: ReportBuildContext | None = None,
) -> SimulationResult:
    """Run one scenario deterministically and persist + self-verify its journal.

    ``seed`` overrides the scenario's registry default and feeds the REAL virtual-swimmer
    RNG (§2.2) — it is never merely reported metadata.
    """
    effective_seed = scenario.defaultSeed if seed is None else seed
    output_dir.mkdir(parents=True, exist_ok=True)

    workout = scenario.workout
    pool = workout.poolLengthM
    total = float(workout.blocks[0].distanceM)
    timeline = compile_ghost_timeline(scenario.profile, workout)
    phases = _phase_lookup(scenario.profile)

    def target_distance_at_active_ms(active_ms: int) -> float:
        sec = active_ms / 1000.0
        if sec <= 0.0:
            return 0.0
        total_sec = timeline.totalActiveDurationSec
        if sec >= total_sec:
            return timeline.totalDistanceM
        return ghost_distance_at_active_time(timeline, sec).distanceM

    def target_speed(d: float) -> float:
        return target_speed_at_distance(timeline, d)

    def phase_type_at_distance(d: float) -> str:
        for from_m, to_m, phase in phases:
            if from_m - 1e-9 <= d <= to_m + 1e-9:
                return phase
        return phases[-1][2]

    stop_window = (
        StopWindow(
            afterLengthIndex=scenario.stop.afterLengthIndex,
            offsetAfterWallMs=scenario.stop.offsetAfterWallMs,
            durationMs=scenario.stop.durationMs,
        )
        if scenario.stop is not None
        else None
    )
    swim = simulate_swim(
        config=VirtualSwimmerConfig(
            seed=effective_seed,
            tickMs=scenario.swimmer.tickMs,
            baseResponseRatio=scenario.swimmer.baseResponseRatio,
            fatigueSlopePer100M=scenario.swimmer.fatigueSlopePer100M,
            noiseStdMps=scenario.swimmer.noiseStdMps,
            minimumActualSpeedMps=scenario.swimmer.minimumActualSpeedMps,
            maximumActualSpeedMps=scenario.swimmer.maximumActualSpeedMps,
            turnDelayMs=scenario.swimmer.turnDelayMs,
        ),
        pool_length_m=pool,
        total_distance_m=total,
        target_distance_at_active_ms=target_distance_at_active_ms,
        target_speed_at_distance=target_speed,
        phase_type_at_distance=phase_type_at_distance,
        stop=stop_window,
        rest=scenario.rest,
        unreliable=scenario.unreliable,
    )

    # ---------------- drive the real aggregate ----------------
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
        workouts_v1_1={workout_ref: workout},
    )

    all_events: list[EventEnvelope] = []
    batches: list[tuple[EventEnvelope, ...]] = []
    commands: list[Command] = []
    outcomes: list[CommandOutcome] = []
    log: JsonlSessionEventLog | None = None

    def drive(command: Command, at_ms: int, *, expect_reject: bool = False) -> int:
        """Apply one command; persist its batch; record its outcome. Returns event count."""
        nonlocal log
        clock.set_to(at_ms)
        commands.append(command)
        already_processed = command.clientCommandId in agg.processedClientCommandIds
        try:
            batch = agg.handle(command)
        except SessionError as exc:
            if not expect_reject:
                raise
            outcomes.append(
                CommandOutcome(
                    clientCommandId=command.clientCommandId,
                    commandType=type(command).__name__,
                    atMs=at_ms,
                    outcome="REJECTED",
                    eventCount=0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            return 0
        if expect_reject:
            raise SimulationError(
                f"command {command.clientCommandId} was expected to be rejected but applied"
            )
        if not batch:
            outcomes.append(
                CommandOutcome(
                    clientCommandId=command.clientCommandId,
                    commandType=type(command).__name__,
                    atMs=at_ms,
                    outcome="APPLIED",
                    eventCount=0,
                )
            )
            return 0
        if already_processed:
            # idempotent replay: the aggregate returned the cached events — nothing new is
            # appended to the journal (exact-duplicate batches are ALREADY_PRESENT).
            outcomes.append(
                CommandOutcome(
                    clientCommandId=command.clientCommandId,
                    commandType=type(command).__name__,
                    atMs=at_ms,
                    outcome="IDEMPOTENT_REPLAY",
                    eventCount=0,
                )
            )
            return 0
        if log is None:
            sid = batch[0].sessionId
            assert sid is not None
            log = JsonlSessionEventLog(output_dir / f"{scenario.scenarioId}.jsonl", sid)
        log.append_batch(batch)
        all_events.extend(batch)
        batches.append(tuple(batch))
        outcomes.append(
            CommandOutcome(
                clientCommandId=command.clientCommandId,
                commandType=type(command).__name__,
                atMs=at_ms,
                outcome="APPLIED",
                eventCount=len(batch),
            )
        )
        return len(batch)

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
    complete_rejected = False
    stop = scenario.stop
    ghost_snapshots: list[GhostSnapshot] = []
    wall_targets_ms = [
        int(
            round(
                target_active_time_at_distance(
                    timeline, min(float(k * pool), total)
                ).elapsedActiveSec
                * 1000.0
            )
        )
        for k in range(1, int(round(total / pool)) + 1)
    ]

    for touch in swim.wallTouches:
        length_index = touch.lengthIndex
        wall_ts = touch.wallTimestampMs

        # coach continuous-curve reset REQUESTED mid-length before this wall
        if (
            scenario.replacementProfile is not None
            and scenario.replacementAfterLengthIndex == length_index - 1
            and not replacement_injected
        ):
            prev_wall_ts = swim.wallTouches[length_index - 1].wallTimestampMs
            request_ts = prev_wall_ts + max((wall_ts - prev_wall_ts) // 2, 1)  # mid-length
            drive(
                CoachPacingReset(
                    clientCommandId=f"reset-{length_index}",
                    sessionId=sid,
                    reason="coach-continuous-curve-reset",
                    replacementPaceProfileRef=replacement_ref,
                ),
                request_ts,
            )
            replacement_injected = True

        at_wall_stop = (
            stop is not None
            and stop.atWallBeforeSplit
            and stop.afterLengthIndex == length_index
            and not stop_injected
        )
        # injected StopPause resolved at this wall (mid-length stop) or AT this wall
        if (
            stop is not None
            and not stop_injected
            and (
                at_wall_stop
                or (not stop.atWallBeforeSplit and stop.afterLengthIndex == length_index - 1)
            )
        ):
            assert swim.stopRealized is not None
            stop_started, stop_end = swim.stopRealized
            confirmed = stop_started + stop.confirmDelayMs
            mark = MarkStopPause(
                clientCommandId=f"stop-{length_index}",
                sessionId=sid,
                trigger=stop.trigger,
                stopStartedAtMs=stop_started,
                confirmedAtMs=confirmed,
                detectionSource=stop.detectionSource,
                detectionQuality=stop.detectionQuality,
                alignmentSource=stop.alignmentSource,
                alignmentQuality=stop.alignmentQuality,
                stopStartTimeQuality=stop.stopStartTimeQuality,
                trackedAlignmentDistanceM=stop.trackedAlignmentDistanceM,
                createdBy="coach",
            )
            drive(mark, confirmed)
            if stop.duplicateMark:
                # identical clientCommandId + identical content → zero new events, zero
                # new journal batches (idempotent replay; §DUPLICATE_STOP_MARK).
                before = len(batches)
                drive(mark, confirmed + 1)
                if len(batches) != before:
                    raise SimulationError("duplicate MarkStopPause produced a new journal batch")
            if scenario.attemptCompleteWhileStopPaused:
                before_events = len(all_events)
                before_batches = len(batches)
                drive(
                    CompleteSession(clientCommandId="complete-early", sessionId=sid),
                    confirmed + 2,
                    expect_reject=True,
                )
                if len(all_events) != before_events or len(batches) != before_batches:
                    raise SimulationError(
                        "rejected CompleteSession mutated the journal or event stream"
                    )
                complete_rejected = True
            # The swimmer resumes when the real stop window ends; the single wall
            # reconciliation then happens at the NEXT official wall's split (mid-length
            # stop) or at this wall's split (at-wall stop).
            resume_ts = max(stop_end, confirmed + 1)
            drive(
                ResolveStopPause(
                    clientCommandId=f"resolve-{length_index}",
                    sessionId=sid,
                    intervalId=f"{sid}-stop-1",
                    resumedAtMs=resume_ts,
                ),
                resume_ts,
            )
            if at_wall_stop:
                # the official wall touch is registered on resume; the stopped span itself
                # is accounted by the StopPause, never by active swim time.
                wall_ts = max(wall_ts, resume_ts)
            stop_injected = True

        drive(
            RecordSplit(
                clientCommandId=f"split-{length_index}",
                sessionId=sid,
                splitId=f"L{length_index}",
                lengthIndex=length_index,
                wallTimestampMs=wall_ts,
                source=SplitSource.SIMULATED,
                distanceM=touch.distanceM,
            ),
            wall_ts,
        )
        ghost_target_ms = wall_targets_ms[length_index]
        ghost_snapshots.append(
            GhostSnapshot(
                lengthIndex=length_index,
                wallTimestampMs=wall_ts,
                ghostTargetActiveMsAtWall=ghost_target_ms,
                swimmerGapMsAtWall=wall_ts - ghost_target_ms,
            )
        )

    last_ts = swim.wallTouches[-1].wallTimestampMs
    drive(CompleteSession(clientCommandId="complete", sessionId=sid), last_ts)

    assert log is not None

    # ---------------- §2.4: harness-internal journal re-read + replay validation ----------
    journal_path = log.path
    reread = JsonlSessionEventLog(journal_path, sid).read_all()
    if reread.notices != ():
        raise SimulationError(f"journal re-read produced recovery notices: {reread.notices}")
    flattened = list(reread.events)
    if [e.seq for e in flattened] != [e.seq for e in all_events]:
        raise SimulationError("journal re-read produced a different event sequence")
    replay = replay_session(flattened)

    # The aggregate exposes the authoritative live ActiveClock. Atomic rollback preserves
    # the shared reference between this object and GhostClock; reading through a workaround
    # would hide a detached aggregate graph instead of detecting it.
    clock_snapshot = agg.activeClock.snapshot(last_ts) if agg.activeClock is not None else None
    live = LiveFinalState(
        sessionId=sid,
        lifecycleState=(agg.state or SessionState.CREATED).value,
        recordedSplitCount=len(agg.recordedSplits),
        officialCompletedDistanceM=float(len(agg.recordedSplits) * pool),
        selectedPaceProfileId=agg.selectedPaceProfileId,
        selectedPaceProfileVersion=agg.selectedPaceProfileVersion,
        selectedPaceProfileSource=agg.selectedPaceProfileSource,
        selectedPaceProfileType=agg.selectedPaceProfileType,
        profileCoachLocked=agg.profileCoachLocked,
        selectedProfileTargetTotalTimeSec=agg.selectedProfileTargetTotalTimeSec,
        selectedCurveRepresentation=agg.selectedCurveRepresentation,
        selectedCurveCompilerVersion=agg.selectedCurveCompilerVersion,
        appliedPaceSecPer100M=agg.appliedPaceTarget,
        openStopPause=agg.openStopPause is not None,
        pendingCoachPacingReset=agg.pendingCoachPacingReset is not None,
        activeDurationMs=(clock_snapshot.activeElapsedMs if clock_snapshot else None),
        stoppedDurationMs=(clock_snapshot.stoppedElapsedMs if clock_snapshot else None),
        wallElapsedMs=(clock_snapshot.wallElapsedMs if clock_snapshot else None),
    )
    st = replay.state
    mismatches: list[str] = []

    def cmp(name: str, live_v: object, replay_v: object) -> None:
        if isinstance(live_v, float) and isinstance(replay_v, float):
            if abs(live_v - replay_v) <= 1e-6:
                return
        elif live_v == replay_v:
            return
        mismatches.append(f"{name}: live={live_v!r} replay={replay_v!r}")

    cmp("sessionId", live.sessionId, st.sessionId)
    cmp("lifecycleState", live.lifecycleState, st.lifecycleState.value)
    cmp("recordedSplitCount", live.recordedSplitCount, len(st.recordedSplits))
    cmp(
        "officialCompletedDistanceM", live.officialCompletedDistanceM, st.officialCompletedDistanceM
    )
    cmp("selectedPaceProfileId", live.selectedPaceProfileId, st.selectedPaceProfileId)
    cmp(
        "selectedPaceProfileVersion", live.selectedPaceProfileVersion, st.selectedPaceProfileVersion
    )
    cmp("selectedPaceProfileSource", live.selectedPaceProfileSource, st.selectedPaceProfileSource)
    cmp("selectedPaceProfileType", live.selectedPaceProfileType, st.selectedPaceProfileType)
    cmp("profileCoachLocked", live.profileCoachLocked, st.profileCoachLocked)
    cmp(
        "selectedProfileTargetTotalTimeSec",
        live.selectedProfileTargetTotalTimeSec,
        st.selectedProfileTargetTotalTimeSec,
    )
    cmp(
        "selectedCurveRepresentation",
        live.selectedCurveRepresentation,
        st.selectedCurveRepresentation,
    )
    cmp(
        "selectedCurveCompilerVersion",
        live.selectedCurveCompilerVersion,
        st.selectedCurveCompilerVersion,
    )
    cmp("openStopPause", live.openStopPause, st.openStopPause is not None)
    cmp(
        "pendingCoachPacingReset",
        live.pendingCoachPacingReset,
        st.pendingCoachPacingReset is not None,
    )
    if mismatches:
        raise SimulationError("live/replay state mismatch: " + "; ".join(mismatches))

    journal_sha = hashlib.sha256(journal_path.read_bytes()).hexdigest()
    scenario_digest = canonical_digest_sha256(scenario)
    workout_digest = canonical_digest_sha256(workout)
    profile_digests = {
        f"{scenario.profile.profileId}:{scenario.profile.profileVersion}": (
            canonical_digest_sha256(scenario.profile)
        )
    }
    if scenario.replacementProfile is not None:
        replacement_key = (
            f"{scenario.replacementProfile.profileId}:{scenario.replacementProfile.profileVersion}"
        )
        profile_digests[replacement_key] = canonical_digest_sha256(scenario.replacementProfile)
    base_report_context = report_context or ReportBuildContext()
    policy_context = replace(
        base_report_context,
        simulatorSynthetic=True,
        simulationRunId=None,
        profileRegistry={},
    )
    analytics_policy_digest = report_policy_digest_sha256(policy_context)
    manifest = build_run_manifest(
        scenario_id=scenario.scenarioId,
        scenario_version=scenario.scenarioVersion,
        scenario_digest=scenario_digest,
        seed=effective_seed,
        harness_version=_SIM_HARNESS_VERSION,
        workout_ref=workout_ref,
        profile=scenario.profile,
        replacement_profile=scenario.replacementProfile,
        workout_digest=workout_digest,
        profile_digests=profile_digests,
        analytics_policy_digest=analytics_policy_digest,
    )
    profile_registry: dict[tuple[str, str], ProfileRuntimeContext] = {
        (scenario.profile.profileId, scenario.profile.profileVersion): ProfileRuntimeContext(
            profile=scenario.profile,
            timeline=timeline,
        )
    }
    if scenario.replacementProfile is not None:
        replacement_timeline = compile_ghost_timeline(scenario.replacementProfile, workout)
        profile_registry[
            (
                scenario.replacementProfile.profileId,
                scenario.replacementProfile.profileVersion,
            )
        ] = ProfileRuntimeContext(
            profile=scenario.replacementProfile,
            timeline=replacement_timeline,
        )
    analytics_observations = tuple(
        SessionObservation(
            timestampMs=item.wallTimeMs,
            estimatedDistanceM=item.actualDistanceM,
            smoothedVelocityMps=item.actualSpeedMps,
            phaseType=item.phaseType,
            quality=item.positionQuality,
            trusted=item.positionQuality in {"HIGH", "MEDIUM"},
            plannedRest=item.plannedRest,
            source="SIMULATOR",
        )
        for item in swim.observations
    )
    effective_report_context = replace(
        base_report_context,
        simulatorSynthetic=True,
        simulationRunId=(base_report_context.simulationRunId or manifest.runId),
        profileRegistry=profile_registry,
    )
    session_report = build_session_report(
        replay_state=replay.state,
        events=tuple(flattened),
        workout=workout,
        pace_profile=scenario.profile,
        compiled_timeline=timeline,
        observations=analytics_observations,
        report_context=effective_report_context,
    )
    session_report_bytes = encode_session_report(session_report)
    second_report = build_session_report(
        replay_state=replay.state,
        events=tuple(flattened),
        workout=workout,
        pace_profile=scenario.profile,
        compiled_timeline=timeline,
        observations=analytics_observations,
        report_context=effective_report_context,
    )
    if encode_session_report(second_report) != session_report_bytes:
        raise SimulationError("same journal produced non-deterministic report bytes")
    session_report_path = output_dir / f"{scenario.scenarioId}-report.json"
    session_report_path.write_bytes(session_report_bytes)
    session_report_sha = hashlib.sha256(session_report_bytes).hexdigest()

    provenance = build_provenance(
        scenario_name=scenario.scenarioId,
        seed=effective_seed,
        session_id=sid,
        harness_version=_SIM_HARNESS_VERSION,
        profile=scenario.profile,
        replacement_profile=scenario.replacementProfile,
        event_count=len(all_events),
    )
    return SimulationResult(
        scenarioId=scenario.scenarioId,
        scenarioVersion=scenario.scenarioVersion,
        seed=effective_seed,
        runId=manifest.runId,
        manifest=manifest,
        sessionId=sid,
        commands=tuple(commands),
        commandOutcomes=tuple(outcomes),
        events=tuple(all_events),
        eventBatches=tuple(batches),
        observations=swim.observations,
        ghostSnapshots=tuple(ghost_snapshots),
        journalPath=journal_path,
        journalSha256=journal_sha,
        liveFinalState=live,
        replayResult=replay,
        replayMatchesLiveState=not mismatches,
        provenance=provenance,
        wallCount=len(swim.wallTouches),
        stopInjected=stop_injected,
        replacementInjected=replacement_injected,
        completeRejectedWhileStopPaused=complete_rejected,
        sessionReport=session_report,
        analyticsObservations=analytics_observations,
        sessionReportBytes=session_report_bytes,
        sessionReportSha256=session_report_sha,
        sessionReportPath=session_report_path,
    )
