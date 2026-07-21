"""Hand-built event-stream builders for replay tests (no aggregate needed)."""

from __future__ import annotations

from contracts.enums import (
    AlignmentSource,
    ControlAdaptationSource,
    ControlDecisionAction,
    EventType,
    PaceRequestSource,
    PaceTargetOrigin,
    ReasonCode,
    SplitQualityFlag,
    SplitSource,
    StopDetectionSource,
    StopPauseTrigger,
    VerificationSource,
)
from contracts.events import (
    CoachPacingResetAppliedPayload,
    CoachPacingResetRequestedPayload,
    ControlDecisionMadePayload,
    EventEnvelope,
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
    StopPauseResolvedPayload,
    StopPauseStartedPayload,
    WorkoutValidatedPayload,
)

SID = "session-r"
POOL = 25


class StreamBuilder:
    """Builds a structurally valid event stream with auto seq/eventId/cid handling."""

    def __init__(self, session_id: str = SID) -> None:
        self.session_id = session_id
        self.events: list[EventEnvelope] = []
        self._seq = 0
        self._cid_n = 0

    def _next_cid(self) -> str:
        self._cid_n += 1
        return f"cmd-{self._cid_n}"

    def add(
        self,
        event_type: EventType,
        payload: object,
        ts: int,
        *,
        cid: str | None = None,
        session_id: str | None = None,
        schema: str = "1.0",
        event_id: str | None = None,
        seq: int | None = None,
    ) -> EventEnvelope:
        self._seq = seq if seq is not None else self._seq + 1
        event = EventEnvelope(
            eventId=event_id or f"evt-{self._seq}",
            seq=self._seq,
            sessionId=session_id if session_id is not None else self.session_id,
            type=event_type,
            tsMs=ts,
            schemaVersion=schema,
            producer="test",
            clientCommandId=cid or self._next_cid(),
            payload=payload,  # type: ignore[arg-type]
        )
        self.events.append(event)
        return event

    # ------------------------------------------------------------------ lifecycle
    def created(self, ts: int = 0, *, pool: int | None = POOL, **kwargs: object) -> StreamBuilder:
        cid = self._next_cid()
        self.add(
            EventType.WorkoutValidated,
            WorkoutValidatedPayload(workoutRef="w1", isValid=True),
            ts,
            cid=cid,
        )
        self.add(
            EventType.SessionCreated,
            SessionCreatedPayload(
                sessionId=self.session_id,
                workoutRef="w1",
                workoutSchemaVersion="1.0",
                poolLengthM=pool,
                **kwargs,  # type: ignore[arg-type]
            ),
            ts,
            cid=cid,
        )
        return self

    def armed(self, ts: int = 0) -> StreamBuilder:
        self.add(EventType.SessionArmed, SessionArmedPayload(sessionId=self.session_id), ts)
        return self

    def started(self, ts: int = 0) -> StreamBuilder:
        self.add(
            EventType.SessionStarted,
            SessionStartedPayload(sessionId=self.session_id, startedAtMs=ts),
            ts,
        )
        return self

    def running(self, ts: int = 0) -> StreamBuilder:
        return self.created(ts).armed(ts).started(ts)

    def paused(self, ts: int) -> StreamBuilder:
        self.add(
            EventType.SessionPaused, SessionPausedPayload(sessionId=self.session_id, atMs=ts), ts
        )
        return self

    def resumed(self, ts: int) -> StreamBuilder:
        self.add(
            EventType.SessionResumed, SessionResumedPayload(sessionId=self.session_id, atMs=ts), ts
        )
        return self

    def completed(self, ts: int) -> StreamBuilder:
        self.add(
            EventType.SessionCompleted,
            SessionCompletedPayload(sessionId=self.session_id, atMs=ts),
            ts,
        )
        return self

    def aborted(self, ts: int) -> StreamBuilder:
        self.add(
            EventType.SessionAborted,
            SessionAbortedPayload(sessionId=self.session_id, atMs=ts, reason=None),
            ts,
        )
        return self

    # ------------------------------------------------------------------ splits
    def split(
        self,
        index: int,
        ts: int,
        *,
        split_id: str | None = None,
        source: SplitSource = SplitSource.TOUCHPAD,
    ) -> StreamBuilder:
        self.add(
            EventType.SplitRecorded,
            SplitRecordedPayload(
                sessionId=self.session_id,
                splitId=split_id or f"split-{index}",
                lengthIndex=index,
                wallTimestampMs=ts,
                source=source,
                qualityFlag=SplitQualityFlag.MANUAL_UNVERIFIED,
            ),
            ts,
        )
        return self

    def verified(
        self,
        index: int,
        ts: int,
        *,
        split_id: str | None = None,
        source: VerificationSource = VerificationSource.SECOND_TIMER,
    ) -> StreamBuilder:
        self.add(
            EventType.SplitVerified,
            SplitVerifiedPayload(
                sessionId=self.session_id,
                splitId=split_id or f"split-{index}",
                lengthIndex=index,
                verificationSource=source,
                verifiedWallTimestampMs=ts,
                manualErrorMs=0,
            ),
            ts,
        )
        return self

    # ------------------------------------------------------------------ StopPause
    def stop_started(
        self,
        *,
        started_at: int,
        confirmed_at: int,
        interval_id: str = f"{SID}-stop-1",
        pending: bool = True,
    ) -> StreamBuilder:
        self.add(
            EventType.StopPauseStarted,
            StopPauseStartedPayload(
                intervalId=interval_id,
                trigger=StopPauseTrigger.MANUAL_INCIDENT,
                startedAtMs=started_at,
                detectionSource=StopDetectionSource.COACH,
                alignmentSource=AlignmentSource.COACH_MARK,
                wallReconciliationPending=pending,
                createdBy="coach",
            ),
            confirmed_at,
        )
        return self

    def stop_resolved(
        self,
        *,
        started_at: int,
        ended_at: int,
        interval_id: str = f"{SID}-stop-1",
        pending: bool = True,
    ) -> StreamBuilder:
        self.add(
            EventType.StopPauseResolved,
            StopPauseResolvedPayload(
                intervalId=interval_id,
                trigger=StopPauseTrigger.MANUAL_INCIDENT,
                startedAtMs=started_at,
                endedAtMs=ended_at,
                durationSec=(ended_at - started_at) / 1000.0,
                detectionSource=StopDetectionSource.COACH,
                alignmentSource=AlignmentSource.COACH_MARK,
                wallReconciliationPending=pending,
                createdBy="coach",
            ),
            ended_at,
        )
        return self

    # ------------------------------------------------------------------ pacing
    def reset_requested(self, ts: int, reason: str | None = "regroup") -> StreamBuilder:
        self.add(
            EventType.CoachPacingResetRequested,
            CoachPacingResetRequestedPayload(sessionId=self.session_id, reason=reason),
            ts,
        )
        return self

    def reset_applied(self, ts: int, effective_from: int = 1) -> StreamBuilder:
        self.add(
            EventType.CoachPacingResetApplied,
            CoachPacingResetAppliedPayload(
                sessionId=self.session_id, effectiveFromLength=effective_from
            ),
            ts,
        )
        return self

    def pace_changed(self, ts: int, pace: float, effective_from: int = 1) -> StreamBuilder:
        self.add(
            EventType.PaceTargetChanged,
            PaceTargetChangedPayload(
                sessionId=self.session_id,
                effectiveFromLength=effective_from,
                appliedPaceSecPer100M=pace,
                origin=PaceTargetOrigin.COACH_OVERRIDE,
            ),
            ts,
        )
        return self

    def decision(self, ts: int, *, applied: float | None = 82.0) -> StreamBuilder:
        self.add(
            EventType.ControlDecisionMade,
            ControlDecisionMadePayload(
                decision=ControlDecisionAction.APPLY,
                reasonCodes=["APPLIED_WITHIN_BOUNDS"],
                reasonCode=ReasonCode.APPLIED,
                adaptationSource=ControlAdaptationSource.none,
                requestSource=PaceRequestSource.COACH_MANUAL,
                suggestedPaceSecPer100M=82.0,
                appliedPaceSecPer100M=applied,
            ),
            ts,
        )
        return self
