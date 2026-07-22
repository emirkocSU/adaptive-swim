"""Pure, deterministic session aggregate: state machine + command orchestration.

Combines the contract models, semantic validator, pace timeline, ActiveClock, GhostClock,
and SafetyController into one in-memory domain flow. No I/O, DB, network, framework,
system clock, or randomness — time and event ids are injected. Input models are never
mutated. Events are produced only as in-memory domain output (persistence/replay = Commit 7).

Accounting: active = ActiveClock active time; stopped = confirmed StopPause intervals;
elapsed = active + stopped. Lifecycle PauseSession time is excluded from active swim time
via a session-level offset and is kept separate from StopPause accounting.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import Any

from contracts.commands import (
    AbortSession,
    ApplyCoachPaceTarget,
    ArmSession,
    CoachPacingReset,
    Command,
    CompleteSession,
    CreateSession,
    MarkStopPause,
    PauseSession,
    RecordSplit,
    ResolveStopPause,
    ResumeSession,
    StartSession,
    VerifySplit,
)
from contracts.continuous_pace import (
    ApprovedContinuousPaceProfile,
    ApprovedPaceProfileVersion,
)
from contracts.enums import (
    AdaptationMode,
    AlignmentQuality,
    AlignmentSource,
    ControlAdaptationSource,
    ControlDecisionAction,
    EventType,
    PaceTargetOrigin,
    ReasonCode,
    SplitQualityFlag,
    StartMode,
    StopDetectionSource,
    StopPauseTrigger,
    StopSignalQuality,
    StopStartTimeQuality,
    Stroke,
)
from contracts.events import Clock as ClockProto
from contracts.events import (
    CoachPacingResetAppliedPayload,
    CoachPacingResetRequestedPayload,
    ControlDecisionMadePayload,
    EventEnvelope,
    EventIdGenerator,
    LongStopConfirmedPayload,
    PaceTargetChangedPayload,
    SessionAbortedPayload,
    SessionArmedPayload,
    SessionCompletedPayload,
    SessionCreatedPayload,
    SessionPausedPayload,
    SessionResumedPayload,
    SessionStartedPayload,
    SplitRecordedPayload,
    SplitVerifiedPayload,
    StopDetectedPayload,
    StopPauseResolvedPayload,
    StopPauseStartedPayload,
    WorkoutValidatedPayload,
)
from contracts.workout import WorkoutTemplateV1_1, WorkoutTemplateVersion
from contracts.workout import WorkoutTemplateVersion as _WTV  # noqa: F401
from swimcore.control import (
    ControlDecision,
    PaceChangeRequest,
    SafetyContext,
    SafetyController,
    SafetyDecision,
    SafetyReasonCode,
)
from swimcore.ghost import GhostClock
from swimcore.pacing import (
    PaceInterval,
    PaceTimeline,
    compile_pace_timeline,
    is_wall_boundary,
    target_pace_at_distance,
)
from swimcore.pacing.continuous_profile_compiler import CONTINUOUS_COMPILER_VERSION
from swimcore.pacing.profile_compiler import (
    compile_live_profile,
)
from swimcore.pacing.profile_selection import (
    ProfileSelectionPolicy,
    select_live_pace_profile,
)
from swimcore.session.errors import (
    CommandIdConflictError,
    InvalidSessionTransitionError,
    InvalidSplitBoundaryError,
    PacingResetAlreadyPendingError,
    PendingReconciliationError,
    SessionError,
    SessionIdMismatchError,
    SessionNotCreatedError,
    SessionWorkoutValidationError,
    SplitNotFoundError,
    SplitVerificationConflictError,
    StopPauseAlreadyOpenError,
    StopPauseIntervalMismatchError,
    StopPauseNotOpenError,
    WorkoutNotCompletedError,
)
from swimcore.session.handler import EventFactory, command_fingerprint
from swimcore.session.state import TERMINAL_STATES, SessionState
from swimcore.session.transitions import next_state
from swimcore.session.types import OpenStopPause, PendingCoachReset, RecordedSplit, VerifiedSplit
from swimcore.time import ActiveClock
from swimcore.workout import WorkoutValidationContext, validate_workout
from swimcore.workout.profile_rules import validate_approved_pace_profile
from swimcore.workout.start_mode import resolve_default_start_mode, resolve_repeat_start_mode

_TOL = 1e-6

_MUTABLE_STATE_FIELDS: tuple[str, ...] = (
    "sessionId",
    "state",
    "workout",
    "paceTimeline",
    "activeClock",
    "ghostClock",
    "appliedPaceTarget",
    "selectedPaceProfileId",
    "selectedPaceProfileVersion",
    "selectedPaceProfileSource",
    "selectedPaceProfileType",
    "profileCoachLocked",
    "selectedProfileTargetTotalTimeSec",
    "selectedCurveRepresentation",
    "selectedCurveCompilerVersion",
    "resolvedStartModes",
    "_sessionStroke",
    "_sessionTotalDistanceM",
    "poolLengthM",
    "workoutGoal",
    "defaultStartMode",
    "pendingCoachPacingReset",
    "recordedSplits",
    "recordedSplitsById",
    "splitIdByLengthIndex",
    "verifiedSplits",
    "openStopPause",
    "processedClientCommandIds",
    "lastWallDistanceM",
    "_stop_counter",
    "_pause_offset_ms",
    "_pause_started_at_ms",
    "_reconciliation_pending",
    "_expected_reconciliation_wall_m",
)


def _split_fingerprint(command: RecordSplit) -> str:
    return command.model_dump_json()


class SessionAggregate:
    def __init__(
        self,
        workouts: Mapping[str, WorkoutTemplateVersion],
        clock: ClockProto,
        id_gen: EventIdGenerator,
        safety: SafetyController | None = None,
        validation_context: WorkoutValidationContext | None = None,
        profiles: Mapping[str, ApprovedPaceProfileVersion] | None = None,
        workouts_v1_1: Mapping[str, WorkoutTemplateV1_1] | None = None,
    ) -> None:
        self._workouts = workouts
        self._profiles: Mapping[str, ApprovedPaceProfileVersion] = profiles or {}
        self._workouts_v1_1: Mapping[str, WorkoutTemplateV1_1] = workouts_v1_1 or {}
        self._clock = clock
        self._events = EventFactory(id_gen)
        self._safety = safety if safety is not None else SafetyController()
        self._ctx = validation_context

        self.sessionId: str | None = None
        self.state: SessionState | None = None
        self.workout: WorkoutTemplateVersion | None = None
        self.paceTimeline: PaceTimeline | None = None
        self.activeClock: ActiveClock | None = None
        self.ghostClock: GhostClock | None = None
        self.appliedPaceTarget: float | None = None
        # --- selected approved-profile metadata (§11); None when running legacy segments ---
        self.selectedPaceProfileId: str | None = None
        self.selectedPaceProfileVersion: str | None = None
        self.selectedPaceProfileSource: str | None = None
        self.selectedPaceProfileType: str | None = None
        self.profileCoachLocked: bool = False
        # --- selected-profile timeline metadata (§2.5) ---
        self.selectedProfileTargetTotalTimeSec: float | None = None
        self.selectedCurveRepresentation: str | None = None
        self.selectedCurveCompilerVersion: str | None = None
        self.resolvedStartModes: dict[int, str] = {}
        self.poolLengthM: int | None = None
        self.workoutGoal: str | None = None
        #: Resolved workout context captured for a continuous-curve replacement (ADR-038).
        self._sessionStroke: Stroke | None = None
        self._sessionTotalDistanceM: float | None = None
        self.defaultStartMode: str | None = None
        self.pendingCoachPacingReset: PendingCoachReset | None = None
        self.recordedSplits: dict[int, RecordedSplit] = {}
        self.recordedSplitsById: dict[str, str] = {}
        self.splitIdByLengthIndex: dict[int, str] = {}
        self.verifiedSplits: dict[int, VerifiedSplit] = {}
        self.openStopPause: OpenStopPause | None = None
        self.processedClientCommandIds: dict[str, tuple[str, list[EventEnvelope]]] = {}
        self.lastWallDistanceM: float = 0.0
        self._stop_counter = 0
        self._pause_offset_ms = 0
        self._pause_started_at_ms: int | None = None
        self._reconciliation_pending = False
        self._expected_reconciliation_wall_m: float | None = None

    # ------------------------------------------------------------------ public
    def handle(self, command: Command) -> list[EventEnvelope]:
        fp = command_fingerprint(command)
        cid = command.clientCommandId
        prior = self.processedClientCommandIds.get(cid)
        if prior is not None:
            stored_fp, stored_events = prior
            if stored_fp != fp:
                raise CommandIdConflictError(f"clientCommandId {cid} reused with different content")
            self._assert_runtime_reference_integrity()
            return list(stored_events)  # idempotent: no mutation, same result

        checkpoint = self._checkpoint_mutable_state()
        try:
            events = self._dispatch(command)
            self._assert_runtime_reference_integrity()
        except Exception:
            self._restore_mutable_state(checkpoint)
            raise
        self.processedClientCommandIds[cid] = (fp, list(events))
        return events

    def _checkpoint_mutable_state(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any], tuple[int, int]]:
        """Snapshot mutable aggregate state before processing a command.

        Session command handling is atomic: if validation, clock/ghost orchestration, or
        event creation fails, the aggregate is restored to this checkpoint. The injected
        clock and external event-id source are not rolled back.
        """
        # Capture both the original references and one deep-copied object graph.  The graph
        # copy preserves aliases inside the checkpoint, while the original references let
        # rollback restore mutable objects *in place*.  Consequently a rejected command
        # changes neither values nor the identity/topology exposed by the aggregate.
        originals = {name: getattr(self, name) for name in _MUTABLE_STATE_FIELDS}
        snapshots = copy.deepcopy(originals)
        return originals, snapshots, self._events.checkpoint()

    def _restore_mutable_state(
        self,
        checkpoint: tuple[dict[str, Any], dict[str, Any], tuple[int, int]],
    ) -> None:
        originals, snapshots, event_checkpoint = checkpoint

        # Restore ordinary fields first. Dicts are restored in place so callers holding a
        # reference to an aggregate collection do not observe a rollback-induced swap.
        for name in _MUTABLE_STATE_FIELDS:
            if name in {"activeClock", "ghostClock"}:
                continue
            original = originals[name]
            snapshot = snapshots[name]
            if isinstance(original, dict) and isinstance(snapshot, dict):
                original.clear()
                original.update(copy.deepcopy(snapshot))
                setattr(self, name, original)
            else:
                setattr(self, name, original)

        # ActiveClock and GhostClock are mutable runtime objects shared by identity. Restore
        # their state in place, then explicitly re-establish the authoritative bindings.
        original_active = originals["activeClock"]
        snapshot_active = snapshots["activeClock"]
        if original_active is not None and snapshot_active is not None:
            original_active.__dict__.clear()
            original_active.__dict__.update(copy.deepcopy(snapshot_active.__dict__))
        self.activeClock = original_active

        original_ghost = originals["ghostClock"]
        snapshot_ghost = snapshots["ghostClock"]
        if original_ghost is not None and snapshot_ghost is not None:
            ghost_state = copy.deepcopy(snapshot_ghost.__dict__)
            ghost_state["_clock"] = self.activeClock
            ghost_state["_timeline"] = self.paceTimeline
            original_ghost.__dict__.clear()
            original_ghost.__dict__.update(ghost_state)
        self.ghostClock = original_ghost

        self._events.restore(event_checkpoint)
        self._assert_runtime_reference_integrity()

    def _assert_runtime_reference_integrity(self) -> None:
        """Reject any detached live runtime graph immediately.

        A started aggregate has one authoritative ActiveClock and one authoritative
        PaceTimeline.  GhostClock must reference those exact objects; equivalent copies are
        not sufficient because later commands mutate the shared runtime instances.
        """
        if self.ghostClock is None:
            return
        if self.activeClock is None or self.paceTimeline is None:
            raise AssertionError("GhostClock exists without aggregate clock/timeline")
        if not self.ghostClock.is_bound_to(
            active_clock=self.activeClock, timeline=self.paceTimeline
        ):
            raise AssertionError("GhostClock detached from aggregate runtime references")

    # ------------------------------------------------------------------ dispatch
    def _dispatch(self, command: Command) -> list[EventEnvelope]:
        if isinstance(command, CreateSession):
            return self._create(command)
        if self.state is None:
            raise SessionNotCreatedError("session not created")
        # session identity: every non-create command must target this aggregate
        cmd_sid = getattr(command, "sessionId", None)
        if cmd_sid != self.sessionId:
            raise SessionIdMismatchError(
                f"command sessionId {cmd_sid} != aggregate {self.sessionId}"
            )
        if isinstance(command, ArmSession):
            return self._lifecycle(command, "ArmSession", EventType.SessionArmed)
        if isinstance(command, StartSession):
            return self._start(command)
        if isinstance(command, PauseSession):
            return self._pause(command)
        if isinstance(command, ResumeSession):
            return self._resume(command)
        if isinstance(command, CompleteSession):
            return self._complete(command)
        if isinstance(command, AbortSession):
            return self._abort(command)
        if isinstance(command, RecordSplit):
            return self._record_split(command)
        if isinstance(command, VerifySplit):
            return self._verify_split(command)
        if isinstance(command, MarkStopPause):
            return self._mark_stop_pause(command)
        if isinstance(command, ResolveStopPause):
            return self._resolve_stop_pause(command)
        if isinstance(command, ApplyCoachPaceTarget):
            return self._apply_pace_target(command)
        if isinstance(command, CoachPacingReset):
            return self._coach_pacing_reset(command)
        raise SessionError(f"unsupported command {type(command).__name__}")

    # ------------------------------------------------------------------ helpers
    def _eff(self, real_ms: int) -> int:
        # During an open lifecycle pause, effective runtime is pinned to the pause start so
        # the ghost/active clock do not advance; the pause is counted immediately, not only
        # on resume.
        base = self._pause_started_at_ms if self._pause_started_at_ms is not None else real_ms
        return base - self._pause_offset_ms

    def _require_running(self, what: str) -> None:
        if self.state is not SessionState.RUNNING:
            raise InvalidSessionTransitionError(f"{what} requires RUNNING (is {self.state})")

    def _emit(
        self, event_type: EventType, payload: object, occurred_at_ms: int, cid: str | None
    ) -> EventEnvelope:
        return self._events.build(event_type, payload, occurred_at_ms, self.sessionId, cid)

    def _current_interval(self) -> PaceInterval:
        """Resolve the current pace interval from the current official distance (2.14)."""
        assert self.paceTimeline is not None
        d = self.lastWallDistanceM
        chosen = self.paceTimeline.intervals[0]
        for interval in self.paceTimeline.intervals:
            if interval.fromM - _TOL <= d < interval.toM - _TOL:
                return interval
            if d >= interval.toM - _TOL:
                chosen = interval
        return chosen

    def _adaptation(
        self,
    ) -> tuple[AdaptationMode, float | None, float | None, float | None]:
        # Profile-run sessions have no 1.0 AdaptationPolicy; live auto-adaptation is off and
        # the coach-approved profile is authoritative (ML/rule cannot auto-apply, §12).
        if self.workout is None:
            return AdaptationMode.off, None, None, None
        # current block resolved from the current interval, not hard-coded blocks[0]
        block = self.workout.blocks[self._current_interval().blockIndex]
        ad = block.adaptation
        if ad is None:
            return AdaptationMode.off, None, None, None
        return (
            ad.mode,
            ad.fastestAllowedPaceSecPer100M,
            ad.slowestAllowedPaceSecPer100M,
            ad.maxChangePercentPerLength,
        )

    # ------------------------------------------------------------------ create
    def _create(self, command: CreateSession) -> list[EventEnvelope]:
        if self.state is not None:
            raise InvalidSessionTransitionError("session already created")

        if command.paceProfileRef is not None:
            return self._create_from_profile(command)

        workout = self._workouts.get(command.workoutRef)
        if workout is None:
            raise SessionWorkoutValidationError(f"unknown workoutRef {command.workoutRef}")
        result = validate_workout(workout, self._ctx)
        if not result.isValid:
            raise SessionWorkoutValidationError(
                f"workout failed semantic validation: {[i.rule for i in result.errors]}"
            )
        try:
            timeline = compile_pace_timeline(workout)
        except Exception as exc:  # noqa: BLE001 - normalized to a domain error, atomic
            raise SessionWorkoutValidationError(f"timeline compilation failed: {exc}") from exc

        # Build ALL events first (event-id generation may fail); only commit aggregate state
        # after the whole batch is produced, so a failure leaves the aggregate untouched (2.8).
        session_id = f"session-{command.clientCommandId}"
        now = self._clock.now_ms()
        events = self._events.build_batch(
            [
                (
                    EventType.WorkoutValidated,
                    WorkoutValidatedPayload(
                        workoutRef=command.workoutRef,
                        isValid=True,
                        errorCount=0,
                        warningCount=len(result.warnings),
                    ),
                    now,
                ),
                (
                    EventType.SessionCreated,
                    SessionCreatedPayload(
                        sessionId=session_id,
                        workoutRef=command.workoutRef,
                        workoutSchemaVersion=workout.schemaVersion,
                        poolLengthM=workout.poolLengthM,
                    ),
                    now,
                ),
            ],
            session_id,
            command.clientCommandId,
        )

        # commit (only after the event batch fully succeeded)
        self.workout = workout
        self.paceTimeline = timeline
        self.sessionId = session_id
        self.poolLengthM = workout.poolLengthM
        # Applied target is the CURRENT interval target, not blocks[0] permanently (2.14):
        # at creation the current distance is 0, so the first interval is the current one.
        self.appliedPaceTarget = timeline.intervals[0].startPaceSecPer100M
        self.state = SessionState.CREATED
        return events

    def _create_from_profile(self, command: CreateSession) -> list[EventEnvelope]:
        """Mainline path: run a coach-approved distance-specific profile (ADR-034).

        Requires a Workout 1.1 (for pool/stroke/start policy) plus an approved profile from
        the aggregate's profile registry. The deterministic core compiles and executes the
        already-approved profile; it never generates one.
        """
        wk11 = self._workouts_v1_1.get(command.workoutRef)
        if wk11 is None:
            raise SessionWorkoutValidationError(
                f"unknown 1.1 workoutRef {command.workoutRef} for profile session"
            )
        result = validate_workout(wk11, self._ctx)
        if not result.isValid:
            raise SessionWorkoutValidationError(
                f"workout 1.1 failed semantic validation: {[i.rule for i in result.errors]}"
            )
        profile = self._profiles.get(command.paceProfileRef or "")
        if profile is None:
            raise SessionWorkoutValidationError(f"unknown paceProfileRef {command.paceProfileRef}")
        # Deterministic profile selection (single candidate here, but the authority order
        # and eligibility still apply so a DRAFT/REJECTED profile cannot start a session).
        try:
            selected = select_live_pace_profile(
                [profile],
                ProfileSelectionPolicy(allowDefaultModelGenerated=command.allowDefaultModelProfile),
            )
        except Exception as exc:  # noqa: BLE001 - normalized to a domain error, atomic
            raise SessionWorkoutValidationError(f"profile not live-eligible: {exc}") from exc
        resolved_start = resolve_repeat_start_mode(wk11, 0, command.firstRepeatIndex)
        # The workout's official total distance for the resolved repeat is the block distance;
        # the profile must cover exactly this, not merely its own declared total.
        block = wk11.blocks[0]
        workout_distance_m = float(block.distanceM)
        # Semantic profile validation surfaces §21 rule codes as machine-readable issues
        # before the deterministic compiler runs. The §21 validator targets the 1.0 leg
        # model; a 1.1 continuous profile is validated by its contract + the continuous
        # compiler's exact reconciliation (ADR-038), so the §21 leg validator is skipped for
        # it (its own authority/pool/start-mode checks still run in the compiler).
        if not isinstance(selected, ApprovedContinuousPaceProfile):
            profile_issues = validate_approved_pace_profile(
                selected,
                pool_length_m=wk11.poolLengthM,
                resolved_start_mode=resolved_start,
                stroke=wk11.stroke,
                workout_distance_m=workout_distance_m,
                allow_default_model=command.allowDefaultModelProfile,
            )
            if profile_issues:
                raise SessionWorkoutValidationError(
                    f"pace profile failed semantic validation: {[i.rule for i in profile_issues]}"
                )
        try:
            timeline = compile_live_profile(
                selected,
                pool_length_m=wk11.poolLengthM,
                resolved_start_mode=resolved_start,
                stroke=wk11.stroke,
                total_distance_m=workout_distance_m,
            )
        except Exception as exc:  # noqa: BLE001 - normalized to a domain error, atomic
            raise SessionWorkoutValidationError(f"profile compilation failed: {exc}") from exc

        session_id = f"session-{command.clientCommandId}"
        default_start_mode = resolve_default_start_mode(wk11).value
        now = self._clock.now_ms()
        # Build the whole event batch before mutating any aggregate field (atomicity, 2.8).
        events = self._events.build_batch(
            [
                (
                    EventType.WorkoutValidated,
                    WorkoutValidatedPayload(
                        workoutRef=command.workoutRef,
                        isValid=True,
                        errorCount=0,
                        warningCount=len(result.warnings),
                    ),
                    now,
                ),
                (
                    EventType.SessionCreated,
                    SessionCreatedPayload(
                        sessionId=session_id,
                        workoutRef=command.workoutRef,
                        workoutSchemaVersion=wk11.schemaVersion,
                        poolLengthM=wk11.poolLengthM,
                        defaultStartMode=default_start_mode,
                        selectedPaceProfileId=selected.profileId,
                        selectedPaceProfileVersion=selected.profileVersion,
                        selectedPaceProfileSource=selected.source.value,
                        selectedPaceProfileType=selected.profileType.value,
                        profileCoachLocked=selected.coachLocked,
                        workoutGoal=wk11.workoutGoal.value,
                        selectedProfileTargetTotalTimeSec=self._profile_timeline_meta(selected)[0],
                        selectedCurveRepresentation=self._profile_timeline_meta(selected)[1],
                        selectedCurveCompilerVersion=self._profile_timeline_meta(selected)[2],
                    ),
                    now,
                ),
            ],
            session_id,
            command.clientCommandId,
        )

        # commit (only after the event batch fully succeeded)
        self.workout = None
        self.paceTimeline = timeline
        self.sessionId = session_id
        self.poolLengthM = wk11.poolLengthM
        self.workoutGoal = wk11.workoutGoal.value
        self.defaultStartMode = default_start_mode
        self.resolvedStartModes = {command.firstRepeatIndex: resolved_start.value}
        self.selectedPaceProfileId = selected.profileId
        self.selectedPaceProfileVersion = selected.profileVersion
        self.selectedPaceProfileSource = selected.source.value
        self.selectedPaceProfileType = selected.profileType.value
        self.profileCoachLocked = selected.coachLocked
        (
            self.selectedProfileTargetTotalTimeSec,
            self.selectedCurveRepresentation,
            self.selectedCurveCompilerVersion,
        ) = self._profile_timeline_meta(selected)
        self._sessionStroke = wk11.stroke
        self._sessionTotalDistanceM = workout_distance_m
        self.appliedPaceTarget = timeline.intervals[0].startPaceSecPer100M
        self.state = SessionState.CREATED
        return events

    # ------------------------------------------------------------------ simple lifecycle
    def _lifecycle(self, command: Command, name: str, event_type: EventType) -> list[EventEnvelope]:
        assert self.state is not None
        dest = next_state(name, self.state)
        now = self._clock.now_ms()
        payload = SessionArmedPayload(sessionId=self._sid())
        event = self._emit(event_type, payload, now, command.clientCommandId)
        self.state = dest
        return [event]

    def _sid(self) -> str:
        assert self.sessionId is not None
        return self.sessionId

    def _start(self, command: StartSession) -> list[EventEnvelope]:
        assert self.state is not None
        dest = next_state("StartSession", self.state)
        now = self._clock.now_ms()
        active = ActiveClock()
        active.start(now)
        assert self.paceTimeline is not None and self.poolLengthM is not None
        ghost = GhostClock(self.paceTimeline, active, self.poolLengthM)
        # commit
        self.activeClock = active
        self.ghostClock = ghost
        self.state = dest
        return [
            self._emit(
                EventType.SessionStarted,
                SessionStartedPayload(
                    sessionId=self._sid(),
                    startedAtMs=now,
                    resolvedFirstStartMode=(
                        self.resolvedStartModes.get(0) or self.defaultStartMode
                    ),
                    targetTotalActiveTimeSec=(
                        self.paceTimeline.totalActiveDurationSec
                        if self.paceTimeline is not None
                        else None
                    ),
                ),
                now,
                command.clientCommandId,
            )
        ]

    def _pause(self, command: PauseSession) -> list[EventEnvelope]:
        assert self.state is not None
        if self.openStopPause is not None:
            raise StopPauseAlreadyOpenError("cannot lifecycle-pause while a StopPause is open")
        dest = next_state("PauseSession", self.state)
        now = self._clock.now_ms()
        self._pause_started_at_ms = now
        self.state = dest
        return [
            self._emit(
                EventType.SessionPaused,
                SessionPausedPayload(sessionId=self._sid(), atMs=now),
                now,
                command.clientCommandId,
            )
        ]

    def _resume(self, command: ResumeSession) -> list[EventEnvelope]:
        assert self.state is not None
        dest = next_state("ResumeSession", self.state)
        now = self._clock.now_ms()
        if self._pause_started_at_ms is not None:
            self._pause_offset_ms += now - self._pause_started_at_ms
            self._pause_started_at_ms = None
        self.state = dest
        return [
            self._emit(
                EventType.SessionResumed,
                SessionResumedPayload(sessionId=self._sid(), atMs=now),
                now,
                command.clientCommandId,
            )
        ]

    def _complete(self, command: CompleteSession) -> list[EventEnvelope]:
        assert self.state is not None
        dest = next_state("CompleteSession", self.state)  # rejects terminal/invalid first
        if self.openStopPause is not None:
            raise StopPauseNotOpenError("cannot complete with an open StopPause")
        if self._reconciliation_pending:
            raise PendingReconciliationError("cannot complete with pending wall reconciliation")
        if self.pendingCoachPacingReset is not None:
            raise WorkoutNotCompletedError("cannot complete with a pending coach pacing reset")
        pool = self._pool()
        total = self.paceTimeline.totalDistanceM if self.paceTimeline is not None else 0.0
        expected_lengths = round(total / pool)
        # every official length split recorded, in order, ending at the final wall
        if len(self.recordedSplits) != expected_lengths:
            raise WorkoutNotCompletedError(
                f"expected {expected_lengths} length splits, have {len(self.recordedSplits)}"
            )
        if any(i not in self.recordedSplits for i in range(expected_lengths)):
            raise WorkoutNotCompletedError("missing an official length split")
        final = self.recordedSplits.get(expected_lengths - 1)
        if final is None or final.distanceM is None or abs(final.distanceM - total) > _TOL:
            raise WorkoutNotCompletedError("final split is not at the workout's final wall")
        now = self._clock.now_ms()
        self.state = dest
        return [
            self._emit(
                EventType.SessionCompleted,
                SessionCompletedPayload(sessionId=self._sid(), atMs=now),
                now,
                command.clientCommandId,
            )
        ]

    def _abort(self, command: AbortSession) -> list[EventEnvelope]:
        assert self.state is not None
        dest = next_state("AbortSession", self.state)
        now = self._clock.now_ms()
        self.openStopPause = None
        self.pendingCoachPacingReset = None
        self._reconciliation_pending = False
        self._expected_reconciliation_wall_m = None
        self.state = dest
        return [
            self._emit(
                EventType.SessionAborted,
                SessionAbortedPayload(sessionId=self._sid(), atMs=now, reason=None),
                now,
                command.clientCommandId,
            )
        ]

    # ------------------------------------------------------------------ splits
    def _record_split(self, command: RecordSplit) -> list[EventEnvelope]:
        self._require_running("RecordSplit")
        pool = self._pool()
        total = self.paceTimeline.totalDistanceM if self.paceTimeline is not None else 0.0
        # --- 2.4 every split must sit on the correct official wall boundary ---
        if command.distanceM is None:
            raise InvalidSplitBoundaryError("split distanceM is required")
        if not math.isfinite(command.distanceM):
            raise InvalidSplitBoundaryError("split distanceM must be finite")
        if not is_wall_boundary(command.distanceM, pool):
            raise InvalidSplitBoundaryError(
                f"{command.distanceM} is not a wall boundary for pool {pool}"
            )
        expected_distance = (command.lengthIndex + 1) * pool
        if abs(command.distanceM - expected_distance) > _TOL:
            raise InvalidSplitBoundaryError(
                f"split distance {command.distanceM} != (lengthIndex+1)*pool {expected_distance}"
            )
        if command.distanceM > total + _TOL:
            raise InvalidSplitBoundaryError(
                f"split distance {command.distanceM} exceeds workout total {total}"
            )
        # --- 2.3 splitId identity (distinct from lengthIndex) ---
        prior = self.recordedSplitsById.get(command.splitId)
        if prior is not None and prior != _split_fingerprint(command):
            raise SplitVerificationConflictError(
                f"splitId {command.splitId} reused with different content"
            )
        existing = self.recordedSplits.get(command.lengthIndex)
        if existing is not None:
            raise SplitVerificationConflictError(
                f"official length {command.lengthIndex} already recorded"
            )
        expected_index = len(self.recordedSplits)
        if command.lengthIndex != expected_index:
            raise InvalidSplitBoundaryError(
                f"split lengthIndex {command.lengthIndex} out of order (expected {expected_index})"
            )
        if self.recordedSplits:
            prev = max(s.wallTimestampMs for s in self.recordedSplits.values())
            if command.wallTimestampMs < prev:
                raise InvalidSessionTransitionError("split wall timestamp not monotonic")

        events: list[EventEnvelope] = []
        assert self.ghostClock is not None
        # pending StopPause reconciliation: reconcile only at the matching wall; earlier
        # official walls still record normally; the expected wall may not be skipped.
        if self._reconciliation_pending:
            expected_wall = self._expected_reconciliation_wall_m
            if expected_wall is not None:
                if command.distanceM > expected_wall + _TOL:
                    raise PendingReconciliationError(
                        f"cannot skip the expected reconciliation wall {expected_wall}"
                    )
                if abs(command.distanceM - expected_wall) <= _TOL:
                    self.ghostClock.reconcile_at_wall(
                        command.distanceM, self._eff(command.wallTimestampMs)
                    )
                    self._reconciliation_pending = False
                    self._expected_reconciliation_wall_m = None

        # pending coach pacing reset applies at this valid wall (moves the ghost anchor)
        events.extend(self._maybe_apply_pending_reset(command))

        split = RecordedSplit(
            lengthIndex=command.lengthIndex,
            wallTimestampMs=command.wallTimestampMs,
            source=command.source.value,
            distanceM=command.distanceM,
            qualityFlag=SplitQualityFlag.MANUAL_UNVERIFIED.value,
        )
        self.recordedSplits[command.lengthIndex] = split
        self.recordedSplitsById[command.splitId] = _split_fingerprint(command)
        self.splitIdByLengthIndex[command.lengthIndex] = command.splitId
        self.lastWallDistanceM = command.distanceM
        events.append(
            self._emit(
                EventType.SplitRecorded,
                SplitRecordedPayload(
                    sessionId=self._sid(),
                    splitId=command.splitId,
                    lengthIndex=command.lengthIndex,
                    wallTimestampMs=command.wallTimestampMs,
                    source=command.source,
                    qualityFlag=SplitQualityFlag.MANUAL_UNVERIFIED,
                ),
                command.wallTimestampMs,
                command.clientCommandId,
            )
        )
        return events

    def _verify_split(self, command: VerifySplit) -> list[EventEnvelope]:
        self._require_running("VerifySplit")
        # verification is keyed by splitId; the length must map to that split
        if command.splitId not in self.recordedSplitsById:
            raise SplitNotFoundError(f"splitId {command.splitId} not recorded")
        if self.splitIdByLengthIndex.get(command.lengthIndex) != command.splitId:
            raise SplitVerificationConflictError(
                f"splitId {command.splitId} does not match length {command.lengthIndex}"
            )
        existing = self.verifiedSplits.get(command.lengthIndex)
        if existing is not None and (
            existing.verificationSource != command.verificationSource.value
            or existing.verifiedWallTimestampMs != command.verifiedWallTimestampMs
        ):
            raise SplitVerificationConflictError(
                f"conflicting verification for splitId {command.splitId}"
            )
        self.verifiedSplits[command.lengthIndex] = VerifiedSplit(
            lengthIndex=command.lengthIndex,
            verificationSource=command.verificationSource.value,
            verifiedWallTimestampMs=command.verifiedWallTimestampMs,
        )
        return [
            self._emit(
                EventType.SplitVerified,
                SplitVerifiedPayload(
                    sessionId=self._sid(),
                    splitId=command.splitId,
                    lengthIndex=command.lengthIndex,
                    verificationSource=command.verificationSource,
                    verifiedWallTimestampMs=command.verifiedWallTimestampMs,
                    manualErrorMs=0,
                ),
                command.verifiedWallTimestampMs,
                command.clientCommandId,
            )
        ]

    # ------------------------------------------------------------------ stop pause
    def _mark_stop_pause(self, command: MarkStopPause) -> list[EventEnvelope]:
        self._require_running("MarkStopPause")
        if self.openStopPause is not None:
            raise StopPauseAlreadyOpenError("a StopPause is already open")
        assert self.ghostClock is not None
        tracked = command.trackedAlignmentDistanceM
        # ghost.apply_stop_pause validates + freezes the clock atomically (alignment checked
        # BEFORE the freeze, so a bad alignment never freezes the active clock). Only after it
        # succeeds do we mutate the counter / open-stop state (atomicity, 2.8).
        self.ghostClock.apply_stop_pause(
            self._eff(command.stopStartedAtMs), self._eff(command.confirmedAtMs), tracked
        )
        self._stop_counter += 1
        interval_id = f"{self._sid()}-stop-{self._stop_counter}"
        self.openStopPause = OpenStopPause(
            intervalId=interval_id,
            trigger=command.trigger.value,
            stopStartedAtMs=command.stopStartedAtMs,
            confirmedAtMs=command.confirmedAtMs,
            trackedAlignmentDistanceM=tracked,
            detectionSource=command.detectionSource.value,
            detectionQuality=command.detectionQuality.value,
            alignmentSource=command.alignmentSource.value,
            alignmentQuality=command.alignmentQuality.value,
            stopStartTimeQuality=command.stopStartTimeQuality.value,
            createdBy=command.createdBy,
            notes=command.notes,
        )
        self._reconciliation_pending = True
        self._expected_reconciliation_wall_m = self.ghostClock.snapshot(
            self._eff(command.confirmedAtMs)
        ).expectedReconciliationWallM

        def base_payload(cls: type, **extra: object) -> object:
            return cls(
                intervalId=interval_id,
                trigger=command.trigger,
                startedAtMs=command.stopStartedAtMs,
                detectionSource=command.detectionSource,
                detectionQuality=command.detectionQuality,
                alignmentSource=command.alignmentSource,
                alignmentQuality=command.alignmentQuality,
                stopStartTimeQuality=command.stopStartTimeQuality,
                wallReconciliationPending=True,
                createdBy=command.createdBy,
                notes=command.notes,
                **extra,
            )

        events: list[EventEnvelope] = []
        auto = command.trigger in (
            StopPauseTrigger.LONG_STOP_THRESHOLD,
            StopPauseTrigger.SENSOR_STOP,
        )
        if auto:
            events.append(
                self._emit(
                    EventType.StopDetected,
                    base_payload(StopDetectedPayload),
                    command.confirmedAtMs,
                    command.clientCommandId,
                )
            )
            events.append(
                self._emit(
                    EventType.LongStopConfirmed,
                    base_payload(
                        LongStopConfirmedPayload,
                        thresholdSec=max(
                            (command.confirmedAtMs - command.stopStartedAtMs) / 1000.0, 0.001
                        ),
                    ),
                    command.confirmedAtMs,
                    command.clientCommandId,
                )
            )
        events.append(
            self._emit(
                EventType.StopPauseStarted,
                base_payload(StopPauseStartedPayload),
                command.confirmedAtMs,
                command.clientCommandId,
            )
        )
        return events

    def _resolve_stop_pause(self, command: ResolveStopPause) -> list[EventEnvelope]:
        self._require_running("ResolveStopPause")
        if self.openStopPause is None:
            raise StopPauseNotOpenError("no open StopPause")
        if command.intervalId != self.openStopPause.intervalId:
            raise StopPauseIntervalMismatchError(
                f"interval {command.intervalId} != open {self.openStopPause.intervalId}"
            )
        assert self.ghostClock is not None
        stop = self.openStopPause
        self.ghostClock.resume_from_stop_pause(self._eff(command.resumedAtMs))
        duration = (command.resumedAtMs - stop.stopStartedAtMs) / 1000.0
        # preserve the ORIGINAL detection metadata; the resolver is a separate actor.
        payload = StopPauseResolvedPayload(
            intervalId=stop.intervalId,
            trigger=StopPauseTrigger(stop.trigger),
            startedAtMs=stop.stopStartedAtMs,
            endedAtMs=command.resumedAtMs,
            durationSec=duration,
            detectionSource=StopDetectionSource(stop.detectionSource),
            detectionQuality=StopSignalQuality(stop.detectionQuality),
            alignmentSource=AlignmentSource(stop.alignmentSource),
            alignmentQuality=AlignmentQuality(stop.alignmentQuality),
            stopStartTimeQuality=StopStartTimeQuality(stop.stopStartTimeQuality),
            wallReconciliationPending=self._reconciliation_pending,
            createdBy=stop.createdBy,
            notes=stop.notes,
        )
        self.openStopPause = None
        return [
            self._emit(
                EventType.StopPauseResolved,
                payload,
                command.resumedAtMs,
                command.clientCommandId,
            )
        ]

    def _detection_source(self) -> StopDetectionSource:
        return StopDetectionSource.COACH

    # ------------------------------------------------------------------ coach pace target (safety-gated)
    def _apply_pace_target(self, command: ApplyCoachPaceTarget) -> list[EventEnvelope]:
        self._require_running("ApplyCoachPaceTarget")
        assert self.appliedPaceTarget is not None
        mode, fastest, slowest, max_change = self._adaptation()
        current_interval = self._current_interval()
        # Current target comes from the current profile leg / segment, never blocks[0].
        current_target = current_interval.startPaceSecPer100M
        wall_distance = (
            command.currentWallDistanceM
            if command.currentWallDistanceM is not None
            else self.lastWallDistanceM
        )
        at_wall = (
            command.isWallBoundary
            if command.isWallBoundary is not None
            else is_wall_boundary(wall_distance, self._pool())
        )
        adaptation_source = self._adaptation_source_for(command.source)
        request = PaceChangeRequest(
            suggestedPaceSecPer100M=command.suggestedPaceSecPer100M,
            source=command.source,
            adaptationSource=adaptation_source,
            confidence=command.confidence,
            inputDataQuality=command.dataQuality,
        )
        context = SafetyContext(
            currentAppliedPaceSecPer100M=self.appliedPaceTarget,
            coachTargetPaceSecPer100M=current_target,
            adaptationMode=mode,
            fastestAllowedPaceSecPer100M=fastest,
            slowestAllowedPaceSecPer100M=slowest,
            maxChangePercentPerLength=max_change,
            currentWallDistanceM=wall_distance,
            isWallBoundary=at_wall,
            coachLocked=self.profileCoachLocked,
            profileSource=self.selectedPaceProfileSource,
            profileCoachLocked=self.profileCoachLocked,
            currentProfileLegIndex=current_interval.profileLegIndex,
            currentTargetPaceSecPer100M=current_target,
        )
        decision = self._safety.decide(request, context)
        now = self._clock.now_ms()
        events = [
            self._emit(
                EventType.ControlDecisionMade,
                ControlDecisionMadePayload(
                    decision=self._decision_action(decision.decision),
                    reasonCodes=[r.value for r in decision.reasonCodes],
                    reasonCode=self._first_reason(decision),
                    adaptationSource=adaptation_source,
                    requestSource=command.source,
                    suggestedPaceSecPer100M=command.suggestedPaceSecPer100M,
                    appliedPaceSecPer100M=(
                        decision.appliedPaceSecPer100M
                        if decision.decision in (SafetyDecision.APPLY, SafetyDecision.BOUNDED_APPLY)
                        else None
                    ),
                    abstained=decision.abstained,
                    bounded=decision.bounded,
                ),
                now,
                command.clientCommandId,
            )
        ]
        if (
            decision.decision
            in (
                SafetyDecision.APPLY,
                SafetyDecision.BOUNDED_APPLY,
            )
            and abs(decision.appliedPaceSecPer100M - self.appliedPaceTarget) > _TOL
        ):
            self.appliedPaceTarget = decision.appliedPaceSecPer100M
            events.append(
                self._emit(
                    EventType.PaceTargetChanged,
                    PaceTargetChangedPayload(
                        sessionId=self._sid(),
                        effectiveFromLength=len(self.recordedSplits),
                        appliedPaceSecPer100M=decision.appliedPaceSecPer100M,
                        origin=self._origin_for(command.source),
                    ),
                    now,
                    command.clientCommandId,
                )
            )
        return events

    @staticmethod
    def _adaptation_source_for(source: object) -> ControlAdaptationSource:
        from contracts.enums import PaceRequestSource

        if source is PaceRequestSource.ML:
            return ControlAdaptationSource.ml
        if source is PaceRequestSource.RULE_BASED:
            return ControlAdaptationSource.rule_based
        return ControlAdaptationSource.none  # COACH_MANUAL is not an ML/rule adaptation

    @staticmethod
    def _origin_for(source: object) -> PaceTargetOrigin:
        from contracts.enums import PaceRequestSource

        if source is PaceRequestSource.ML:
            return PaceTargetOrigin.ML_ADAPTATION
        if source is PaceRequestSource.RULE_BASED:
            return PaceTargetOrigin.RULE_ADAPTATION
        return PaceTargetOrigin.COACH_OVERRIDE

    def _decision_action(self, d: SafetyDecision) -> ControlDecisionAction:
        return {
            SafetyDecision.APPLY: ControlDecisionAction.APPLY,
            SafetyDecision.BOUNDED_APPLY: ControlDecisionAction.CLAMP,
            SafetyDecision.ABSTAIN_USE_COACH_PLAN: ControlDecisionAction.KEEP_PLAN,
            SafetyDecision.REJECT: ControlDecisionAction.REJECT,
        }[d]

    def _first_reason(self, decision: ControlDecision) -> ReasonCode:
        # loss-less full list lives in payload.reasonCodes; this single field is the primary
        # reason for legacy consumers, via an exhaustive mapping (no silent default).
        primary = decision.reasonCodes[0]
        mapping = {
            SafetyReasonCode.MODE_OFF: ReasonCode.ADAPTATION_OFF,
            SafetyReasonCode.SUGGEST_ONLY: ReasonCode.ADAPTATION_OFF,
            SafetyReasonCode.LOW_CONFIDENCE: ReasonCode.LOW_CONFIDENCE,
            SafetyReasonCode.LOW_DATA_QUALITY: ReasonCode.SENSOR_QUALITY,
            SafetyReasonCode.NOT_AT_WALL_BOUNDARY: ReasonCode.ADAPTATION_OFF,
            SafetyReasonCode.BOUNDED_BY_FASTEST_LIMIT: ReasonCode.CLAMPED_TO_BOUNDS,
            SafetyReasonCode.BOUNDED_BY_SLOWEST_LIMIT: ReasonCode.CLAMPED_TO_BOUNDS,
            SafetyReasonCode.BOUNDED_BY_MAX_CHANGE: ReasonCode.CLAMPED_TO_BOUNDS,
            SafetyReasonCode.INVALID_SUGGESTION: ReasonCode.OUT_OF_DISTRIBUTION,
            SafetyReasonCode.COACH_PLAN_FALLBACK: ReasonCode.ADAPTATION_OFF,
            SafetyReasonCode.APPLIED_WITHIN_BOUNDS: ReasonCode.APPLIED,
            SafetyReasonCode.HEART_RATE_ONLY_REJECTED: ReasonCode.SENSOR_QUALITY,
            SafetyReasonCode.COACH_PROFILE_LOCKED: ReasonCode.COACH_PROFILE_LOCKED,
            SafetyReasonCode.ML_CONFIDENCE_MISSING: ReasonCode.ML_CONFIDENCE_MISSING,
            SafetyReasonCode.DATA_QUALITY_MISSING: ReasonCode.DATA_QUALITY_MISSING,
            SafetyReasonCode.PROFILE_SOURCE_NOT_ELIGIBLE: ReasonCode.PROFILE_SOURCE_NOT_ELIGIBLE,
            SafetyReasonCode.CURRENT_PROFILE_LEG_TARGET: ReasonCode.CURRENT_PROFILE_LEG_TARGET,
        }
        # Exhaustive: any unmapped SafetyReasonCode is a programming error, not a silent
        # default. This will raise (KeyError) in tests if a new code is added without a map.
        missing = set(SafetyReasonCode) - set(mapping)
        if missing:
            raise SessionError(f"unmapped SafetyReasonCode(s): {sorted(m.value for m in missing)}")
        return mapping[primary]

    # ------------------------------------------------------------------ profile metadata
    @staticmethod
    def _profile_timeline_meta(
        profile: ApprovedPaceProfileVersion,
    ) -> tuple[float, str | None, str | None]:
        """(targetTotalTimeSec, curveRepresentation, curveCompilerVersion) for a profile."""
        if isinstance(profile, ApprovedContinuousPaceProfile):
            return (
                profile.targetTimeConstraint.targetTotalTimeSec,
                profile.curve.representation.value,
                CONTINUOUS_COMPILER_VERSION,
            )
        return (profile.targetTotalTimeSec, None, None)

    # ------------------------------------------------------------------ coach pacing reset
    def _coach_pacing_reset(self, command: CoachPacingReset) -> list[EventEnvelope]:
        self._require_running("CoachPacingReset")
        if (
            self.pendingCoachPacingReset is not None
            and self.pendingCoachPacingReset.reason != command.reason
        ):
            raise PacingResetAlreadyPendingError(
                "a different coach pacing reset is already pending"
            )
        pool = self._pool()
        applied_after = len(self.recordedSplits)
        expected_wall = (applied_after + 1) * pool

        # Optional continuous-curve replacement (ADR-038): resolve, authority-check and
        # compile NOW; if anything fails the whole command is rejected atomically (no event).
        replacement_timeline: PaceTimeline | None = None
        replacement_id: str | None = None
        replacement_version: str | None = None
        replacement_target: float | None = None
        replacement_source: str | None = None
        replacement_type: str | None = None
        replacement_lock: bool | None = None
        replacement_repr: str | None = None
        replacement_compiler: str | None = None
        if command.replacementPaceProfileRef is not None:
            replacement = self._profiles.get(command.replacementPaceProfileRef)
            if replacement is None:
                raise SessionWorkoutValidationError(
                    f"unknown replacement paceProfileRef {command.replacementPaceProfileRef}"
                )
            try:
                selected = select_live_pace_profile(
                    [replacement],
                    ProfileSelectionPolicy(allowDefaultModelGenerated=False),
                )
            except Exception as exc:  # noqa: BLE001 - normalized to a domain error, atomic
                raise SessionWorkoutValidationError(
                    f"replacement profile not live-eligible: {exc}"
                ) from exc
            resolved_start_val = self.resolvedStartModes.get(0) or self.defaultStartMode
            assert resolved_start_val is not None
            assert self._sessionStroke is not None and self._sessionTotalDistanceM is not None
            if selected.poolLengthM != pool:
                raise SessionWorkoutValidationError("replacement profile pool mismatch")
            if selected.stroke is not self._sessionStroke:
                raise SessionWorkoutValidationError("replacement profile stroke mismatch")
            if selected.startMode.value != resolved_start_val:
                raise SessionWorkoutValidationError("replacement profile start-mode mismatch")
            try:
                replacement_timeline = compile_live_profile(
                    selected,
                    pool_length_m=pool,
                    resolved_start_mode=StartMode(resolved_start_val),
                    stroke=self._sessionStroke,
                    total_distance_m=self._sessionTotalDistanceM,
                )
            except Exception as exc:  # noqa: BLE001 - normalized to a domain error, atomic
                raise SessionWorkoutValidationError(
                    f"replacement profile compilation failed: {exc}"
                ) from exc
            replacement_id = selected.profileId
            replacement_version = selected.profileVersion
            replacement_target = replacement_timeline.totalActiveDurationSec
            replacement_source = selected.source.value
            replacement_type = selected.profileType.value
            replacement_lock = selected.coachLocked
            _target, replacement_repr, replacement_compiler = self._profile_timeline_meta(selected)

        self.pendingCoachPacingReset = PendingCoachReset(
            clientCommandId=command.clientCommandId,
            reason=command.reason,
            requestedAfterLengthIndex=applied_after,
            expectedApplicationWallM=float(expected_wall),
            requestedBy="coach",
            replacementTimeline=replacement_timeline,
            replacementProfileId=replacement_id,
            replacementProfileVersion=replacement_version,
            replacementTargetTotalTimeSec=replacement_target,
            previousProfileId=self.selectedPaceProfileId,
            previousProfileVersion=self.selectedPaceProfileVersion,
            replacementProfileSource=replacement_source,
            replacementProfileType=replacement_type,
            replacementProfileCoachLocked=replacement_lock,
            replacementCurveRepresentation=replacement_repr,
            replacementCurveCompilerVersion=replacement_compiler,
        )
        now = self._clock.now_ms()
        return [
            self._emit(
                EventType.CoachPacingResetRequested,
                CoachPacingResetRequestedPayload(
                    sessionId=self._sid(),
                    reason=command.reason,
                    replacementPaceProfileId=replacement_id,
                    replacementPaceProfileVersion=replacement_version,
                    replacementTargetTotalTimeSec=replacement_target,
                    replacementPaceProfileSource=replacement_source,
                    replacementPaceProfileType=replacement_type,
                    replacementProfileCoachLocked=replacement_lock,
                    replacementCurveRepresentation=replacement_repr,
                    replacementCurveCompilerVersion=replacement_compiler,
                ),
                now,
                command.clientCommandId,
            )
        ]

    def _maybe_apply_pending_reset(self, split: RecordSplit) -> list[EventEnvelope]:
        pending = self.pendingCoachPacingReset
        if pending is None:
            return []
        # apply only at the immediate next valid official wall (distanceM already validated)
        if pending.expectedApplicationWallM is None or (
            split.distanceM is None
            or abs(split.distanceM - pending.expectedApplicationWallM) > _TOL
        ):
            return []  # not the reset's wall yet; keep pending
        assert self.ghostClock is not None
        if pending.replacementTimeline is not None:
            # continuous-curve replacement: swap the timeline in at this wall (no StopPause,
            # no clock freeze), then adopt the new profile metadata for downstream state.
            new_timeline = pending.replacementTimeline
            assert isinstance(new_timeline, PaceTimeline)
            self.ghostClock.apply_timeline_reset_at_wall(
                new_timeline, split.distanceM, self._eff(split.wallTimestampMs)
            )
            self.paceTimeline = new_timeline
            # §2.5: the swap adopts ALL selected-profile state fields from the replacement.
            self.selectedPaceProfileId = pending.replacementProfileId
            self.selectedPaceProfileVersion = pending.replacementProfileVersion
            self.selectedPaceProfileSource = pending.replacementProfileSource
            self.selectedPaceProfileType = pending.replacementProfileType
            if pending.replacementProfileCoachLocked is not None:
                self.profileCoachLocked = pending.replacementProfileCoachLocked
            self.selectedProfileTargetTotalTimeSec = pending.replacementTargetTotalTimeSec
            self.selectedCurveRepresentation = pending.replacementCurveRepresentation
            self.selectedCurveCompilerVersion = pending.replacementCurveCompilerVersion
            # Applied target = replacement timeline's current target just after this wall.
            applied_after_wall = target_pace_at_distance(new_timeline, split.distanceM)
            self.appliedPaceTarget = applied_after_wall
        else:
            # plain pace realignment: move the ghost display anchor to this wall
            self.ghostClock.apply_coach_pacing_reset_at_wall(
                split.distanceM, self._eff(split.wallTimestampMs)
            )
        applied_payload = CoachPacingResetAppliedPayload(
            sessionId=self._sid(),
            effectiveFromLength=split.lengthIndex,
            previousPaceProfileId=pending.previousProfileId,
            previousPaceProfileVersion=pending.previousProfileVersion,
            replacementPaceProfileId=pending.replacementProfileId,
            replacementPaceProfileVersion=pending.replacementProfileVersion,
            replacementTargetTotalTimeSec=pending.replacementTargetTotalTimeSec,
            replacementPaceProfileSource=pending.replacementProfileSource,
            replacementPaceProfileType=pending.replacementProfileType,
            replacementProfileCoachLocked=pending.replacementProfileCoachLocked,
            replacementAppliedPaceSecPer100M=(
                self.appliedPaceTarget if pending.replacementTimeline is not None else None
            ),
            replacementCurveRepresentation=pending.replacementCurveRepresentation,
            replacementCurveCompilerVersion=pending.replacementCurveCompilerVersion,
        )
        self.pendingCoachPacingReset = None
        return [
            self._emit(
                EventType.CoachPacingResetApplied,
                applied_payload,
                split.wallTimestampMs,
                split.clientCommandId,
            )
        ]

    # ------------------------------------------------------------------ misc
    def _wk(self) -> WorkoutTemplateVersion:
        assert self.workout is not None
        return self.workout

    def _pool(self) -> int:
        """Pool length for either path (legacy 1.0 workout or approved-profile session)."""
        assert self.poolLengthM is not None
        return self.poolLengthM

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES
