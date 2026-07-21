"""Historical read-model state produced by pure replay (Commit 7).

This is a *historical read model*, not a live aggregate: it cannot receive commands, it has
no clocks, and it never rewinds the runtime ActiveClock/GhostClock. All durations are
integer milliseconds derived exclusively from event payloads.
"""

from __future__ import annotations

from dataclasses import dataclass

from swimcore.session.state import SessionState


@dataclass(frozen=True, slots=True)
class HistoricalRecordedSplit:
    splitId: str
    lengthIndex: int
    wallTimestampMs: int
    source: str
    qualityFlag: str
    #: Official distance derived from pool geometry ((lengthIndex+1) * poolLengthM).
    #: Never taken from a wearable estimate. ``None`` only if the pool length is unknown.
    officialDistanceM: float | None


@dataclass(frozen=True, slots=True)
class HistoricalVerifiedSplit:
    splitId: str
    lengthIndex: int
    verificationSource: str
    verifiedWallTimestampMs: int
    manualErrorMs: int


@dataclass(frozen=True, slots=True)
class HistoricalStopPauseInterval:
    intervalId: str
    trigger: str
    #: Real (retroactive) stop start from the payload — NOT the confirmation event time.
    startedAtMs: int
    #: ``None`` while the interval is still open at the replay horizon.
    endedAtMs: int | None
    durationMs: int | None
    detectionSource: str
    createdBy: str
    notes: str | None
    wallReconciliationPendingAtResolve: bool


@dataclass(frozen=True, slots=True)
class HistoricalControlDecision:
    decision: str
    reasonCodes: tuple[str, ...]
    reasonCode: str
    adaptationSource: str
    requestSource: str
    suggestedPaceSecPer100M: float | None
    appliedPaceSecPer100M: float | None
    abstained: bool
    bounded: bool


@dataclass(frozen=True, slots=True)
class HistoricalPendingCoachReset:
    requestedAtSeq: int
    reason: str | None


@dataclass(frozen=True, slots=True)
class HistoricalSessionState:
    sessionId: str
    lifecycleState: SessionState
    workoutRef: str | None
    workoutSchemaVersion: str | None
    poolLengthM: int | None
    defaultStartMode: str | None
    selectedPaceProfileId: str | None
    selectedPaceProfileVersion: str | None
    selectedPaceProfileSource: str | None
    selectedPaceProfileType: str | None
    profileCoachLocked: bool
    workoutGoal: str | None
    startedAtMs: int | None
    endedAtMs: int | None
    lastSeq: int
    lastEventTimestampMs: int
    recordedSplits: tuple[HistoricalRecordedSplit, ...]
    verifiedSplits: tuple[HistoricalVerifiedSplit, ...]
    officialCompletedLengthCount: int
    officialCompletedDistanceM: float | None
    openStopPause: HistoricalStopPauseInterval | None
    completedStopPauses: tuple[HistoricalStopPauseInterval, ...]
    wallReconciliationPending: bool
    pendingCoachPacingReset: HistoricalPendingCoachReset | None
    appliedPaceSecPer100M: float | None
    lastControlDecision: HistoricalControlDecision | None
    activeDurationMs: int
    stoppedDurationMs: int
    lifecyclePausedDurationMs: int
    elapsedDurationMs: int
    wallDurationMs: int
    processedClientCommandIds: tuple[str, ...]
    recoveryCount: int = 0


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Outcome of a pure historical replay."""

    state: HistoricalSessionState
    eventsApplied: int
