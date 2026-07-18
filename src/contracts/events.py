"""Event contracts + deterministic time/id abstractions.

Every event carries a *typed* payload model (no free ``dict``). ``EventEnvelope`` enforces
that the ``EventType`` matches its payload model, so an empty, free-form, or mismatched
payload is rejected.

Event ordering uses a session-monotonic ``seq``; the ``eventId`` is independent. In
Phase 1 a ULID is not required — a ``uuid4`` string is acceptable for ``eventId``, and
ordering is done with ``seq``.

The ``Clock`` / ``TimestampProvider`` / ``EventIdGenerator`` protocols are placed here at
contract level (minimal, no implementation). The simulator/tests supply deterministic
implementations (SimClock, deterministic id generator) in later commits.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import model_validator

from contracts._base import (
    NonEmptyStr,
    NonNegFloat,
    NonNegInt,
    PaceValue,
    PosFloat,
    SeqInt,
    StrictModel,
    approx_equal,
)
from contracts.enums import (
    AlignmentQuality,
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
    StopSignalQuality,
    StopStartTimeQuality,
    VerificationSource,
)
from contracts.version import EVENT_ENVELOPE_SCHEMA_VERSION


# --------------------------------------------------------------------------- session payloads
class WorkoutValidatedPayload(StrictModel):
    workoutRef: NonEmptyStr
    isValid: bool
    errorCount: NonNegInt = 0
    warningCount: NonNegInt = 0


class SessionCreatedPayload(StrictModel):
    sessionId: NonEmptyStr
    workoutRef: NonEmptyStr


class SessionArmedPayload(StrictModel):
    sessionId: NonEmptyStr


class SessionStartedPayload(StrictModel):
    sessionId: NonEmptyStr
    startedAtMs: NonNegInt


class SessionPausedPayload(StrictModel):
    sessionId: NonEmptyStr
    atMs: NonNegInt


class SessionResumedPayload(StrictModel):
    sessionId: NonEmptyStr
    atMs: NonNegInt


class SessionCompletedPayload(StrictModel):
    sessionId: NonEmptyStr
    atMs: NonNegInt


class SessionAbortedPayload(StrictModel):
    sessionId: NonEmptyStr
    atMs: NonNegInt
    reason: str | None = None


# --------------------------------------------------------------------------- split payloads
class SplitRecordedPayload(StrictModel):
    sessionId: NonEmptyStr
    splitId: NonEmptyStr
    lengthIndex: NonNegInt
    wallTimestampMs: NonNegInt
    source: SplitSource
    qualityFlag: SplitQualityFlag


class SplitVerifiedPayload(StrictModel):
    sessionId: NonEmptyStr
    splitId: NonEmptyStr
    lengthIndex: NonNegInt
    verificationSource: VerificationSource
    verifiedWallTimestampMs: NonNegInt
    manualErrorMs: int


# --------------------------------------------------------------------------- stop-pause payloads
class _StopPausePayload(StrictModel):
    """Shared StopPause event fields. Requiredness is tightened per event subclass."""

    intervalId: NonEmptyStr
    trigger: StopPauseTrigger
    startedAtMs: NonNegInt
    endedAtMs: NonNegInt | None = None
    durationSec: NonNegFloat | None = None
    relatedSetIndex: NonNegInt | None = None
    relatedRepeatIndex: NonNegInt | None = None
    relatedLengthIndex: NonNegInt | None = None
    detectionSource: StopDetectionSource
    detectionQuality: StopSignalQuality = StopSignalQuality.UNKNOWN
    alignmentSource: AlignmentSource = AlignmentSource.UNKNOWN
    alignmentQuality: AlignmentQuality = AlignmentQuality.UNKNOWN
    stopStartTimeQuality: StopStartTimeQuality = StopStartTimeQuality.UNKNOWN
    wallReconciliationPending: bool = False
    createdBy: NonEmptyStr
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_time_relationship(self) -> _StopPausePayload:
        if self.endedAtMs is not None:
            if self.endedAtMs < self.startedAtMs:
                raise ValueError("endedAtMs must be >= startedAtMs")
            if self.durationSec is None:
                raise ValueError("a resolved stop (endedAtMs set) requires durationSec")
            expected = (self.endedAtMs - self.startedAtMs) / 1000.0
            if not approx_equal(self.durationSec, expected):
                raise ValueError(
                    "durationSec must match (endedAtMs - startedAtMs) / 1000 "
                    f"(got {self.durationSec}, expected {expected})"
                )
        return self


class StopDetectedPayload(_StopPausePayload):
    """Open detection — endedAtMs/durationSec may be None."""


class LongStopConfirmedPayload(_StopPausePayload):
    thresholdSec: PosFloat


class StopPauseStartedPayload(_StopPausePayload):
    """StopPause opened; may start mid-pool (wallReconciliationPending)."""


class StopPauseResolvedPayload(_StopPausePayload):
    endedAtMs: NonNegInt
    durationSec: NonNegFloat


# --------------------------------------------------------------------------- pacing payloads
class PaceTargetChangedPayload(StrictModel):
    sessionId: NonEmptyStr
    effectiveFromLength: NonNegInt
    appliedPaceSecPer100M: PaceValue
    origin: PaceTargetOrigin


class CoachPacingResetRequestedPayload(StrictModel):
    sessionId: NonEmptyStr
    reason: str | None = None


class CoachPacingResetAppliedPayload(StrictModel):
    sessionId: NonEmptyStr
    effectiveFromLength: NonNegInt


class ControlDecisionMadePayload(StrictModel):
    decision: ControlDecisionAction
    #: Full, loss-less list of safety reason codes (never empty).
    reasonCodes: list[NonEmptyStr]
    reasonCode: ReasonCode
    adaptationSource: ControlAdaptationSource
    requestSource: PaceRequestSource = PaceRequestSource.COACH_MANUAL
    suggestedPaceSecPer100M: PaceValue | None = None
    appliedPaceSecPer100M: PaceValue | None = None
    abstained: bool = False
    bounded: bool = False

    @model_validator(mode="after")
    def _reason_codes_not_empty(self) -> ControlDecisionMadePayload:
        if not self.reasonCodes:
            raise ValueError("reasonCodes must not be empty")
        return self


EventPayload = (
    WorkoutValidatedPayload
    | SessionCreatedPayload
    | SessionArmedPayload
    | SessionStartedPayload
    | SessionPausedPayload
    | SessionResumedPayload
    | SessionCompletedPayload
    | SessionAbortedPayload
    | SplitRecordedPayload
    | SplitVerifiedPayload
    | StopDetectedPayload
    | LongStopConfirmedPayload
    | StopPauseStartedPayload
    | StopPauseResolvedPayload
    | PaceTargetChangedPayload
    | CoachPacingResetRequestedPayload
    | CoachPacingResetAppliedPayload
    | ControlDecisionMadePayload
)

#: Exactly one payload model per event type.
PAYLOAD_FOR_EVENT: dict[EventType, type[StrictModel]] = {
    EventType.WorkoutValidated: WorkoutValidatedPayload,
    EventType.SessionCreated: SessionCreatedPayload,
    EventType.SessionArmed: SessionArmedPayload,
    EventType.SessionStarted: SessionStartedPayload,
    EventType.SessionPaused: SessionPausedPayload,
    EventType.SessionResumed: SessionResumedPayload,
    EventType.SessionCompleted: SessionCompletedPayload,
    EventType.SessionAborted: SessionAbortedPayload,
    EventType.SplitRecorded: SplitRecordedPayload,
    EventType.SplitVerified: SplitVerifiedPayload,
    EventType.StopDetected: StopDetectedPayload,
    EventType.LongStopConfirmed: LongStopConfirmedPayload,
    EventType.StopPauseStarted: StopPauseStartedPayload,
    EventType.StopPauseResolved: StopPauseResolvedPayload,
    EventType.PaceTargetChanged: PaceTargetChangedPayload,
    EventType.CoachPacingResetRequested: CoachPacingResetRequestedPayload,
    EventType.CoachPacingResetApplied: CoachPacingResetAppliedPayload,
    EventType.ControlDecisionMade: ControlDecisionMadePayload,
}
# SessionRecovered is a replay-only marker handled in a later commit; it carries no
# domain payload contract here.


class EventEnvelope(StrictModel):
    eventId: NonEmptyStr
    seq: SeqInt
    sessionId: str | None = None
    type: EventType
    tsMs: NonNegInt
    wallTs: NonNegInt | None = None
    schemaVersion: str = EVENT_ENVELOPE_SCHEMA_VERSION
    producer: NonEmptyStr
    clientCommandId: str | None = None
    causationId: str | None = None
    payload: EventPayload

    @model_validator(mode="before")
    @classmethod
    def _coerce_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "type" in data and "payload" in data:
            try:
                etype = EventType(data["type"])
            except ValueError:
                return data  # let the `type` field raise the enum error
            model = PAYLOAD_FOR_EVENT.get(etype)
            payload = data["payload"]
            if model is not None and isinstance(payload, dict):
                data = {**data, "payload": model(**payload)}
        return data

    @model_validator(mode="after")
    def _payload_matches_type(self) -> EventEnvelope:
        expected = PAYLOAD_FOR_EVENT.get(self.type)
        if expected is None:
            raise ValueError(f"event type {self.type} has no typed payload contract")
        if not isinstance(self.payload, expected):
            raise ValueError(
                f"payload {type(self.payload).__name__} does not match event type {self.type}"
            )
        return self


# --------------------------------------------------------------------------- abstractions
@runtime_checkable
class Clock(Protocol):
    """Monotonic clock source, in milliseconds. Injected into pure logic."""

    def now_ms(self) -> int: ...


@runtime_checkable
class TimestampProvider(Protocol):
    """Best-effort wall-clock timestamp source, in milliseconds."""

    def wall_now_ms(self) -> int: ...


@runtime_checkable
class EventIdGenerator(Protocol):
    """Produces unique event ids (uuid4 in Phase 1; deterministic in tests)."""

    def next_id(self) -> str: ...
