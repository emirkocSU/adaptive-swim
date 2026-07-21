"""Pure historical session replay (Commit 7).

``replay_session`` folds typed domain events into a :class:`HistoricalSessionState`.

What replay is NOT:
- it does not execute commands (``SessionAggregate.handle`` is never called);
- it does not rewind or drive the runtime ``ActiveClock`` / ``GhostClock`` / ``SimClock``;
- it does not use real time, randomness, ids, or any I/O;
- it does not reconstruct an exact mid-pool ghost metre position — mid-pool alignment is a
  temporary display concern; official accounting is wall-derived.

Duration model (all integer milliseconds, derived only from event payloads):

    horizon               = terminal event time (COMPLETED/ABORTED) or last event time
    wallDurationMs        = horizon - sessionStartedAtMs
    lifecyclePausedDurationMs = completed lifecycle-pause intervals
                              (+ open interval to horizon if still PAUSED)
    stoppedDurationMs     = resolved StopPause intervals
                              (+ open StopPause: startedAtMs → horizon)
    elapsedDurationMs     = wallDurationMs - lifecyclePausedDurationMs
    activeDurationMs      = elapsedDurationMs - stoppedDurationMs

The retroactive StopPause start comes from the payload ``startedAtMs``; the confirmation
event's own timestamp is never mistaken for the stop start. Lifecycle pause and StopPause
are separate axes: a StopPause never changes the lifecycle state (session stays RUNNING)
and lifecycle-paused time is never added to ``stoppedDurationMs``.
"""

from __future__ import annotations

from collections.abc import Sequence

from contracts.enums import EventType
from contracts.events import (
    CoachPacingResetAppliedPayload,
    CoachPacingResetRequestedPayload,
    ControlDecisionMadePayload,
    EventEnvelope,
    PaceTargetChangedPayload,
    SessionAbortedPayload,
    SessionCompletedPayload,
    SessionCreatedPayload,
    SessionPausedPayload,
    SessionRecoveredPayload,
    SessionResumedPayload,
    SessionStartedPayload,
    SplitRecordedPayload,
    SplitVerifiedPayload,
    StopPauseResolvedPayload,
    StopPauseStartedPayload,
)
from swimcore.replay.errors import (
    ReplayDurationError,
    ReplaySplitError,
    ReplayStopPauseError,
    ReplayTransitionError,
)
from swimcore.replay.state import (
    HistoricalControlDecision,
    HistoricalPendingCoachReset,
    HistoricalRecordedSplit,
    HistoricalSessionState,
    HistoricalStopPauseInterval,
    HistoricalVerifiedSplit,
    ReplayResult,
)
from swimcore.replay.validation import validate_event_stream
from swimcore.session.errors import InvalidSessionTransitionError
from swimcore.session.state import TERMINAL_STATES, SessionState
from swimcore.session.transitions import next_state

#: Lifecycle event → the command name in the authoritative transition table. The replay
#: reuses ``swimcore.session.transitions`` so a second transition table never exists.
_LIFECYCLE_COMMAND_FOR_EVENT: dict[EventType, str] = {
    EventType.SessionArmed: "ArmSession",
    EventType.SessionStarted: "StartSession",
    EventType.SessionPaused: "PauseSession",
    EventType.SessionResumed: "ResumeSession",
    EventType.SessionCompleted: "CompleteSession",
    EventType.SessionAborted: "AbortSession",
}

#: Events accepted before ``SessionCreated`` (metadata-only validation output).
_PRE_CREATE_EVENTS = frozenset({EventType.WorkoutValidated})

#: Events that require lifecycle RUNNING (mirrors the aggregate's ``_require_running``).
_RUNNING_ONLY_EVENTS = frozenset(
    {
        EventType.SplitRecorded,
        EventType.SplitVerified,
        EventType.StopDetected,
        EventType.LongStopConfirmed,
        EventType.StopPauseStarted,
        EventType.StopPauseResolved,
        EventType.PaceTargetChanged,
        EventType.CoachPacingResetRequested,
        EventType.CoachPacingResetApplied,
        EventType.ControlDecisionMade,
    }
)


class _Fold:
    """Mutable fold accumulator; frozen into HistoricalSessionState at the end."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.created = False
        self.lifecycle: SessionState | None = None
        self.workout_ref: str | None = None
        self.workout_schema_version: str | None = None
        self.pool_length_m: int | None = None
        self.default_start_mode: str | None = None
        self.profile_id: str | None = None
        self.profile_version: str | None = None
        self.profile_source: str | None = None
        self.profile_type: str | None = None
        self.profile_coach_locked = False
        self.workout_goal: str | None = None
        self.started_at_ms: int | None = None
        self.ended_at_ms: int | None = None
        self.splits: list[HistoricalRecordedSplit] = []
        self.splits_by_id: dict[str, HistoricalRecordedSplit] = {}
        self.split_id_by_length: dict[int, str] = {}
        self.verified: dict[int, HistoricalVerifiedSplit] = {}
        self.open_stop: HistoricalStopPauseInterval | None = None
        self.completed_stops: list[HistoricalStopPauseInterval] = []
        self.wall_reconciliation_pending = False
        self.pending_reset: HistoricalPendingCoachReset | None = None
        self.applied_pace: float | None = None
        self.last_decision: HistoricalControlDecision | None = None
        self.open_pause_started_at_ms: int | None = None
        self.lifecycle_paused_ms = 0
        self.command_ids: list[str] = []
        self.command_id_seen: set[str] = set()
        self.recovery_count = 0


def _transition(fold: _Fold, event_type: EventType, seq: int) -> SessionState:
    assert fold.lifecycle is not None
    command_name = _LIFECYCLE_COMMAND_FOR_EVENT[event_type]
    try:
        return next_state(command_name, fold.lifecycle)
    except InvalidSessionTransitionError as exc:
        raise ReplayTransitionError(f"event seq {seq}: {exc}") from exc


def _apply_created(fold: _Fold, payload: SessionCreatedPayload, seq: int) -> None:
    if fold.created:
        raise ReplayTransitionError(f"event seq {seq}: session already created")
    if payload.sessionId != fold.session_id:
        raise ReplayTransitionError(
            f"event seq {seq}: SessionCreated payload sessionId {payload.sessionId!r} "
            f"!= stream sessionId {fold.session_id!r}"
        )
    fold.created = True
    fold.lifecycle = SessionState.CREATED
    fold.workout_ref = payload.workoutRef
    fold.workout_schema_version = payload.workoutSchemaVersion
    fold.pool_length_m = payload.poolLengthM
    fold.default_start_mode = payload.defaultStartMode
    fold.profile_id = payload.selectedPaceProfileId
    fold.profile_version = payload.selectedPaceProfileVersion
    fold.profile_source = payload.selectedPaceProfileSource
    fold.profile_type = payload.selectedPaceProfileType
    fold.profile_coach_locked = payload.profileCoachLocked
    fold.workout_goal = payload.workoutGoal


def _apply_split_recorded(fold: _Fold, payload: SplitRecordedPayload, seq: int) -> None:
    if payload.splitId in fold.splits_by_id:
        raise ReplaySplitError(f"event seq {seq}: splitId {payload.splitId!r} already recorded")
    expected_index = len(fold.splits)
    if payload.lengthIndex != expected_index:
        raise ReplaySplitError(
            f"event seq {seq}: split lengthIndex {payload.lengthIndex} out of order "
            f"(expected {expected_index})"
        )
    if fold.splits and payload.wallTimestampMs < fold.splits[-1].wallTimestampMs:
        raise ReplaySplitError(
            f"event seq {seq}: split wall timestamp {payload.wallTimestampMs} not monotonic"
        )
    # Official distance is derived from workout/pool geometry ONLY. A wearable's estimated
    # metres never appears here and never rewrites the official distance (ADR-036).
    official = (
        float((payload.lengthIndex + 1) * fold.pool_length_m)
        if fold.pool_length_m is not None
        else None
    )
    split = HistoricalRecordedSplit(
        splitId=payload.splitId,
        lengthIndex=payload.lengthIndex,
        wallTimestampMs=payload.wallTimestampMs,
        source=payload.source.value,
        qualityFlag=payload.qualityFlag.value,
        officialDistanceM=official,
    )
    fold.splits.append(split)
    fold.splits_by_id[payload.splitId] = split
    fold.split_id_by_length[payload.lengthIndex] = payload.splitId
    # A pending StopPause wall reconciliation closes at the next official wall split.
    if fold.wall_reconciliation_pending:
        fold.wall_reconciliation_pending = False


def _apply_split_verified(fold: _Fold, payload: SplitVerifiedPayload, seq: int) -> None:
    if payload.splitId not in fold.splits_by_id:
        raise ReplaySplitError(
            f"event seq {seq}: SplitVerified before SplitRecorded for {payload.splitId!r}"
        )
    if fold.split_id_by_length.get(payload.lengthIndex) != payload.splitId:
        raise ReplaySplitError(
            f"event seq {seq}: splitId {payload.splitId!r} does not match length "
            f"{payload.lengthIndex}"
        )
    verified = HistoricalVerifiedSplit(
        splitId=payload.splitId,
        lengthIndex=payload.lengthIndex,
        verificationSource=payload.verificationSource.value,
        verifiedWallTimestampMs=payload.verifiedWallTimestampMs,
        manualErrorMs=payload.manualErrorMs,
    )
    existing = fold.verified.get(payload.lengthIndex)
    if existing is not None:
        if existing != verified:
            raise ReplaySplitError(
                f"event seq {seq}: conflicting second verification for {payload.splitId!r}"
            )
        return  # identical re-verification is idempotent
    fold.verified[payload.lengthIndex] = verified


def _apply_stop_pause_started(fold: _Fold, payload: StopPauseStartedPayload, seq: int) -> None:
    if fold.open_stop is not None:
        raise ReplayStopPauseError(
            f"event seq {seq}: a StopPause ({fold.open_stop.intervalId}) is already open"
        )
    if fold.open_pause_started_at_ms is not None:
        raise ReplayStopPauseError(
            f"event seq {seq}: open lifecycle pause and open StopPause together — corrupt stream"
        )
    if fold.completed_stops and payload.startedAtMs < (fold.completed_stops[-1].endedAtMs or 0):
        raise ReplayStopPauseError(
            f"event seq {seq}: StopPause start {payload.startedAtMs} overlaps the previous "
            f"interval ending at {fold.completed_stops[-1].endedAtMs}"
        )
    fold.open_stop = HistoricalStopPauseInterval(
        intervalId=payload.intervalId,
        trigger=payload.trigger.value,
        startedAtMs=payload.startedAtMs,
        endedAtMs=None,
        durationMs=None,
        detectionSource=payload.detectionSource.value,
        createdBy=payload.createdBy,
        notes=payload.notes,
        wallReconciliationPendingAtResolve=payload.wallReconciliationPending,
    )
    if payload.wallReconciliationPending:
        fold.wall_reconciliation_pending = True


def _apply_stop_pause_resolved(fold: _Fold, payload: StopPauseResolvedPayload, seq: int) -> None:
    open_stop = fold.open_stop
    if open_stop is None:
        raise ReplayStopPauseError(f"event seq {seq}: StopPauseResolved without an open StopPause")
    if payload.intervalId != open_stop.intervalId:
        raise ReplayStopPauseError(
            f"event seq {seq}: resolve intervalId {payload.intervalId!r} != open "
            f"{open_stop.intervalId!r}"
        )
    if payload.startedAtMs != open_stop.startedAtMs:
        raise ReplayStopPauseError(
            f"event seq {seq}: resolve startedAtMs {payload.startedAtMs} != open interval "
            f"start {open_stop.startedAtMs}"
        )
    if payload.endedAtMs < payload.startedAtMs:
        raise ReplayStopPauseError(
            f"event seq {seq}: StopPause end {payload.endedAtMs} before start {payload.startedAtMs}"
        )
    completed = HistoricalStopPauseInterval(
        intervalId=open_stop.intervalId,
        trigger=open_stop.trigger,
        startedAtMs=open_stop.startedAtMs,
        endedAtMs=payload.endedAtMs,
        durationMs=payload.endedAtMs - payload.startedAtMs,
        detectionSource=open_stop.detectionSource,
        createdBy=open_stop.createdBy,
        notes=open_stop.notes,
        wallReconciliationPendingAtResolve=payload.wallReconciliationPending,
    )
    fold.completed_stops.append(completed)
    fold.open_stop = None
    # Wall reconciliation stays pending until the next official wall split.


def _apply_event(fold: _Fold, event: EventEnvelope) -> None:
    etype = event.type
    payload = event.payload
    seq = event.seq

    if etype is EventType.SessionRecovered:
        # Explicit recovery marker: never changes lifecycle state.
        assert isinstance(payload, SessionRecoveredPayload)
        if not fold.created:
            raise ReplayTransitionError(f"event seq {seq}: SessionRecovered before SessionCreated")
        fold.recovery_count += 1
        return

    if fold.lifecycle in TERMINAL_STATES:
        raise ReplayTransitionError(
            f"event seq {seq}: {etype.value} after terminal state {fold.lifecycle}"
        )

    if not fold.created:
        if etype in _PRE_CREATE_EVENTS:
            return  # metadata only
        if etype is EventType.SessionCreated:
            assert isinstance(payload, SessionCreatedPayload)
            _apply_created(fold, payload, seq)
            return
        raise ReplayTransitionError(f"event seq {seq}: {etype.value} before SessionCreated")

    if etype in _RUNNING_ONLY_EVENTS and fold.lifecycle is not SessionState.RUNNING:
        raise ReplayTransitionError(
            f"event seq {seq}: {etype.value} requires RUNNING (is {fold.lifecycle})"
        )

    if etype is EventType.SessionCreated:
        assert isinstance(payload, SessionCreatedPayload)
        _apply_created(fold, payload, seq)  # raises: already created
    elif etype is EventType.WorkoutValidated:
        return  # metadata only
    elif etype is EventType.SessionArmed:
        fold.lifecycle = _transition(fold, etype, seq)
    elif etype is EventType.SessionStarted:
        assert isinstance(payload, SessionStartedPayload)
        fold.lifecycle = _transition(fold, etype, seq)
        fold.started_at_ms = payload.startedAtMs
    elif etype is EventType.SessionPaused:
        assert isinstance(payload, SessionPausedPayload)
        if fold.open_stop is not None:
            raise ReplayStopPauseError(
                f"event seq {seq}: lifecycle pause while a StopPause is open — corrupt stream"
            )
        fold.lifecycle = _transition(fold, etype, seq)
        fold.open_pause_started_at_ms = payload.atMs
    elif etype is EventType.SessionResumed:
        assert isinstance(payload, SessionResumedPayload)
        fold.lifecycle = _transition(fold, etype, seq)
        pause_start = fold.open_pause_started_at_ms
        if pause_start is None:
            raise ReplayTransitionError(f"event seq {seq}: SessionResumed without an open pause")
        if payload.atMs < pause_start:
            raise ReplayDurationError(
                f"event seq {seq}: resume time {payload.atMs} before pause start {pause_start}"
            )
        fold.lifecycle_paused_ms += payload.atMs - pause_start
        fold.open_pause_started_at_ms = None
    elif etype is EventType.SessionCompleted:
        assert isinstance(payload, SessionCompletedPayload)
        if fold.open_stop is not None:
            raise ReplayStopPauseError(f"event seq {seq}: SessionCompleted with an open StopPause")
        fold.lifecycle = _transition(fold, etype, seq)
        fold.ended_at_ms = payload.atMs
    elif etype is EventType.SessionAborted:
        assert isinstance(payload, SessionAbortedPayload)
        fold.lifecycle = _transition(fold, etype, seq)
        fold.ended_at_ms = payload.atMs
        if fold.open_pause_started_at_ms is not None:
            if payload.atMs < fold.open_pause_started_at_ms:
                raise ReplayDurationError(
                    f"event seq {seq}: abort time {payload.atMs} before pause start "
                    f"{fold.open_pause_started_at_ms}"
                )
            fold.lifecycle_paused_ms += payload.atMs - fold.open_pause_started_at_ms
            fold.open_pause_started_at_ms = None
        # An open StopPause is kept as open historical state; its duration is counted to
        # the abort horizon (the clock was frozen until the session ended).
    elif etype is EventType.SplitRecorded:
        assert isinstance(payload, SplitRecordedPayload)
        _apply_split_recorded(fold, payload, seq)
    elif etype is EventType.SplitVerified:
        assert isinstance(payload, SplitVerifiedPayload)
        _apply_split_verified(fold, payload, seq)
    elif etype in (EventType.StopDetected, EventType.LongStopConfirmed):
        return  # detection markers preceding StopPauseStarted; no state change
    elif etype is EventType.StopPauseStarted:
        assert isinstance(payload, StopPauseStartedPayload)
        _apply_stop_pause_started(fold, payload, seq)
    elif etype is EventType.StopPauseResolved:
        assert isinstance(payload, StopPauseResolvedPayload)
        _apply_stop_pause_resolved(fold, payload, seq)
    elif etype is EventType.PaceTargetChanged:
        assert isinstance(payload, PaceTargetChangedPayload)
        fold.applied_pace = payload.appliedPaceSecPer100M
    elif etype is EventType.CoachPacingResetRequested:
        assert isinstance(payload, CoachPacingResetRequestedPayload)
        if fold.pending_reset is not None and fold.pending_reset.reason != payload.reason:
            raise ReplayTransitionError(
                f"event seq {seq}: a different coach pacing reset is already pending"
            )
        fold.pending_reset = HistoricalPendingCoachReset(requestedAtSeq=seq, reason=payload.reason)
    elif etype is EventType.CoachPacingResetApplied:
        assert isinstance(payload, CoachPacingResetAppliedPayload)
        if fold.pending_reset is None:
            raise ReplayTransitionError(
                f"event seq {seq}: CoachPacingResetApplied without a pending reset"
            )
        # A coach reset is NOT a StopPause: it changes no stopped duration and deletes no
        # recorded splits — it only closes the pending marker. When the reset carried a
        # continuous-curve replacement (ADR-038), adopt the new profile id/version so the
        # historical read model reflects the swap from this wall onward.
        if payload.replacementPaceProfileId is not None:
            fold.profile_id = payload.replacementPaceProfileId
            fold.profile_version = payload.replacementPaceProfileVersion
        fold.pending_reset = None
    elif etype is EventType.ControlDecisionMade:
        assert isinstance(payload, ControlDecisionMadePayload)
        fold.last_decision = HistoricalControlDecision(
            decision=payload.decision.value,
            reasonCodes=tuple(payload.reasonCodes),
            reasonCode=payload.reasonCode.value,
            adaptationSource=payload.adaptationSource.value,
            requestSource=payload.requestSource.value,
            suggestedPaceSecPer100M=payload.suggestedPaceSecPer100M,
            appliedPaceSecPer100M=payload.appliedPaceSecPer100M,
            abstained=payload.abstained,
            bounded=payload.bounded,
        )
    else:
        # Pace-profile lifecycle events (§13) are plan-level metadata authored by a later
        # UI/ML phase; they change no runtime session state in the historical read model.
        return


def _durations(fold: _Fold, horizon_ms: int) -> tuple[int, int, int, int, int]:
    if fold.started_at_ms is None:
        return 0, 0, 0, 0, 0
    wall = horizon_ms - fold.started_at_ms
    if wall < 0:
        raise ReplayDurationError(
            f"horizon {horizon_ms} precedes session start {fold.started_at_ms}"
        )
    paused = fold.lifecycle_paused_ms
    if fold.open_pause_started_at_ms is not None:  # still PAUSED at the horizon
        if horizon_ms < fold.open_pause_started_at_ms:
            raise ReplayDurationError("horizon precedes the open lifecycle pause start")
        paused += horizon_ms - fold.open_pause_started_at_ms
    stopped = 0
    for interval in fold.completed_stops:
        assert interval.durationMs is not None
        stopped += interval.durationMs
    if fold.open_stop is not None:
        if horizon_ms < fold.open_stop.startedAtMs:
            raise ReplayDurationError("horizon precedes the open StopPause start")
        stopped += horizon_ms - fold.open_stop.startedAtMs
    elapsed = wall - paused
    active = elapsed - stopped
    if paused < 0 or stopped < 0 or elapsed < 0 or active < 0:
        raise ReplayDurationError(
            f"contradictory durations: wall={wall} paused={paused} stopped={stopped} "
            f"elapsed={elapsed} active={active}"
        )
    if elapsed != active + stopped or wall != elapsed + paused:
        raise ReplayDurationError("duration invariants violated")  # pragma: no cover
    return active, stopped, paused, elapsed, wall


def replay_session(
    events: Sequence[EventEnvelope],
    *,
    expected_session_id: str | None = None,
) -> ReplayResult:
    """Fold a validated event stream into a historical read model (pure)."""
    session_id = validate_event_stream(events, expected_session_id=expected_session_id)
    fold = _Fold(session_id)

    for event in events:
        cid = event.clientCommandId
        if cid is not None and cid not in fold.command_id_seen:
            fold.command_id_seen.add(cid)
            fold.command_ids.append(cid)
        _apply_event(fold, event)

    if not fold.created or fold.lifecycle is None:
        raise ReplayTransitionError("stream contains no SessionCreated event")

    last_event = events[-1]
    horizon = fold.ended_at_ms if fold.ended_at_ms is not None else last_event.tsMs
    active, stopped, paused, elapsed, wall = _durations(fold, horizon)

    pool = fold.pool_length_m
    official_count = len(fold.splits)
    official_distance = float(official_count * pool) if pool is not None else None

    state = HistoricalSessionState(
        sessionId=session_id,
        lifecycleState=fold.lifecycle,
        workoutRef=fold.workout_ref,
        workoutSchemaVersion=fold.workout_schema_version,
        poolLengthM=fold.pool_length_m,
        defaultStartMode=fold.default_start_mode,
        selectedPaceProfileId=fold.profile_id,
        selectedPaceProfileVersion=fold.profile_version,
        selectedPaceProfileSource=fold.profile_source,
        selectedPaceProfileType=fold.profile_type,
        profileCoachLocked=fold.profile_coach_locked,
        workoutGoal=fold.workout_goal,
        startedAtMs=fold.started_at_ms,
        endedAtMs=fold.ended_at_ms,
        lastSeq=last_event.seq,
        lastEventTimestampMs=last_event.tsMs,
        recordedSplits=tuple(fold.splits),
        verifiedSplits=tuple(fold.verified[k] for k in sorted(fold.verified)),
        officialCompletedLengthCount=official_count,
        officialCompletedDistanceM=official_distance,
        openStopPause=fold.open_stop,
        completedStopPauses=tuple(fold.completed_stops),
        wallReconciliationPending=fold.wall_reconciliation_pending,
        pendingCoachPacingReset=fold.pending_reset,
        appliedPaceSecPer100M=fold.applied_pace,
        lastControlDecision=fold.last_decision,
        activeDurationMs=active,
        stoppedDurationMs=stopped,
        lifecyclePausedDurationMs=paused,
        elapsedDurationMs=elapsed,
        wallDurationMs=wall,
        processedClientCommandIds=tuple(fold.command_ids),
        recoveryCount=fold.recovery_count,
    )
    return ReplayResult(state=state, eventsApplied=len(events))
