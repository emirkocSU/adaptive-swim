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

import math
from collections.abc import Mapping

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
    StopDetectionSource,
    StopPauseTrigger,
    StopSignalQuality,
    StopStartTimeQuality,
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
from contracts.workout import WorkoutTemplateVersion
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
from swimcore.pacing import PaceInterval, PaceTimeline, compile_pace_timeline, is_wall_boundary
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

_TOL = 1e-6


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
    ) -> None:
        self._workouts = workouts
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
            return list(stored_events)  # idempotent: no mutation, same result

        events = self._dispatch(command)
        self.processedClientCommandIds[cid] = (fp, list(events))
        return events

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
        assert self.workout is not None
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

        # commit
        self.workout = workout
        self.paceTimeline = timeline
        self.sessionId = f"session-{command.clientCommandId}"
        self.appliedPaceTarget = workout.blocks[0].segments[0].targetPaceSecPer100M
        now = self._clock.now_ms()
        events = [
            self._emit(
                EventType.WorkoutValidated,
                WorkoutValidatedPayload(
                    workoutRef=command.workoutRef,
                    isValid=True,
                    errorCount=0,
                    warningCount=len(result.warnings),
                ),
                now,
                command.clientCommandId,
            ),
            self._emit(
                EventType.SessionCreated,
                SessionCreatedPayload(sessionId=self.sessionId, workoutRef=command.workoutRef),
                now,
                command.clientCommandId,
            ),
        ]
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
        assert self.paceTimeline is not None and self.workout is not None
        ghost = GhostClock(self.paceTimeline, active, self.workout.poolLengthM)
        # commit
        self.activeClock = active
        self.ghostClock = ghost
        self.state = dest
        return [
            self._emit(
                EventType.SessionStarted,
                SessionStartedPayload(sessionId=self._sid(), startedAtMs=now),
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
        pool = self._wk().poolLengthM
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
        pool = self._wk().poolLengthM
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
        wall_distance = (
            command.currentWallDistanceM
            if command.currentWallDistanceM is not None
            else self.lastWallDistanceM
        )
        at_wall = (
            command.isWallBoundary
            if command.isWallBoundary is not None
            else is_wall_boundary(wall_distance, self._wk().poolLengthM)
        )
        request = PaceChangeRequest(
            suggestedPaceSecPer100M=command.suggestedPaceSecPer100M,
            source=command.source,
            adaptationSource=ControlAdaptationSource.rule_based,
            confidence=command.confidence,
            inputDataQuality=command.dataQuality,
        )
        context = SafetyContext(
            currentAppliedPaceSecPer100M=self.appliedPaceTarget,
            coachTargetPaceSecPer100M=self.appliedPaceTarget,
            adaptationMode=mode,
            fastestAllowedPaceSecPer100M=fastest,
            slowestAllowedPaceSecPer100M=slowest,
            maxChangePercentPerLength=max_change,
            currentWallDistanceM=wall_distance,
            isWallBoundary=at_wall,
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
                    adaptationSource=ControlAdaptationSource.rule_based,
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
                        origin=PaceTargetOrigin.COACH_OVERRIDE,
                    ),
                    now,
                    command.clientCommandId,
                )
            )
        return events

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
        }
        return mapping[primary]

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
        pool = self._wk().poolLengthM
        applied_after = len(self.recordedSplits)
        expected_wall = (applied_after + 1) * pool
        self.pendingCoachPacingReset = PendingCoachReset(
            clientCommandId=command.clientCommandId,
            reason=command.reason,
            requestedAfterLengthIndex=applied_after,
            expectedApplicationWallM=float(expected_wall),
            requestedBy="coach",
        )
        now = self._clock.now_ms()
        return [
            self._emit(
                EventType.CoachPacingResetRequested,
                CoachPacingResetRequestedPayload(sessionId=self._sid(), reason=command.reason),
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
        # move the ghost display anchor to this wall (no StopPause, no clock freeze)
        self.ghostClock.apply_coach_pacing_reset_at_wall(
            split.distanceM, self._eff(split.wallTimestampMs)
        )
        self.pendingCoachPacingReset = None
        return [
            self._emit(
                EventType.CoachPacingResetApplied,
                CoachPacingResetAppliedPayload(
                    sessionId=self._sid(), effectiveFromLength=split.lengthIndex
                ),
                split.wallTimestampMs,
                split.clientCommandId,
            )
        ]

    # ------------------------------------------------------------------ misc
    def _wk(self) -> WorkoutTemplateVersion:
        assert self.workout is not None
        return self.workout

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES
