"""Command contracts.

Every command carries ``clientCommandId`` for idempotency. ``CoachPacingReset`` is NOT a
StopPause: it does not erase previous poor performance; it only starts a new pacing
reference at the next valid wall boundary.
"""

from __future__ import annotations

from typing import Literal

from contracts._base import NonEmptyStr, NonNegFloat, NonNegInt, PaceValue, StrictModel, UnitRatio
from contracts.enums import (
    AlignmentQuality,
    AlignmentSource,
    PaceRequestSource,
    SplitSource,
    StopDetectionSource,
    StopPauseTrigger,
    StopSignalQuality,
    StopStartTimeQuality,
    VerificationSource,
)


class Command(StrictModel):
    """Base command; ``commandType`` is a discriminating literal on each subclass."""

    clientCommandId: NonEmptyStr


class CreateSession(Command):
    commandType: Literal["CreateSession"] = "CreateSession"
    workoutRef: str
    #: Optional mainline selection: an approved pace-profile ref (from the aggregate's
    #: profile registry) and the resolved repeat to run first. When present, the session
    #: runs the approved distance-specific profile instead of legacy 1.0 segments.
    paceProfileRef: str | None = None
    firstRepeatIndex: NonNegInt = 0
    allowDefaultModelProfile: bool = False


class ArmSession(Command):
    commandType: Literal["ArmSession"] = "ArmSession"
    sessionId: str


class StartSession(Command):
    commandType: Literal["StartSession"] = "StartSession"
    sessionId: str


class PauseSession(Command):
    commandType: Literal["PauseSession"] = "PauseSession"
    sessionId: str


class ResumeSession(Command):
    commandType: Literal["ResumeSession"] = "ResumeSession"
    sessionId: str


class AbortSession(Command):
    commandType: Literal["AbortSession"] = "AbortSession"
    sessionId: str


class CompleteSession(Command):
    commandType: Literal["CompleteSession"] = "CompleteSession"
    sessionId: str


class RecordSplit(Command):
    commandType: Literal["RecordSplit"] = "RecordSplit"
    sessionId: str
    splitId: NonEmptyStr
    lengthIndex: NonNegInt
    wallTimestampMs: NonNegInt
    source: SplitSource
    #: Wall distance for this split; required and must be a valid wall boundary.
    distanceM: NonNegFloat


class VerifySplit(Command):
    commandType: Literal["VerifySplit"] = "VerifySplit"
    sessionId: str
    splitId: NonEmptyStr
    lengthIndex: int
    verificationSource: VerificationSource
    verifiedWallTimestampMs: NonNegInt


class MarkStopPause(Command):
    commandType: Literal["MarkStopPause"] = "MarkStopPause"
    sessionId: str
    trigger: StopPauseTrigger
    stopStartedAtMs: NonNegInt
    confirmedAtMs: NonNegInt
    detectionSource: StopDetectionSource
    detectionQuality: StopSignalQuality = StopSignalQuality.UNKNOWN
    alignmentSource: AlignmentSource = AlignmentSource.TRACKED_POSITION
    alignmentQuality: AlignmentQuality = AlignmentQuality.UNKNOWN
    stopStartTimeQuality: StopStartTimeQuality = StopStartTimeQuality.UNKNOWN
    trackedAlignmentDistanceM: NonNegFloat = 0.0
    createdBy: NonEmptyStr = "coach"
    notes: str | None = None


class ResolveStopPause(Command):
    commandType: Literal["ResolveStopPause"] = "ResolveStopPause"
    sessionId: str
    intervalId: str
    resumedAtMs: NonNegInt
    alignmentSource: AlignmentSource = AlignmentSource.WALL_RECONCILIATION
    resolvedBy: str | None = None
    resolutionNotes: str | None = None


class ApplyCoachPaceTarget(Command):
    commandType: Literal["ApplyCoachPaceTarget"] = "ApplyCoachPaceTarget"
    sessionId: str
    suggestedPaceSecPer100M: PaceValue
    source: PaceRequestSource = PaceRequestSource.COACH_MANUAL
    reason: str | None = None
    requestedBy: NonEmptyStr = "coach"
    confidence: UnitRatio | None = None
    dataQuality: UnitRatio | None = None
    currentWallDistanceM: NonNegFloat | None = None
    isWallBoundary: bool | None = None


class CoachPacingReset(Command):
    commandType: Literal["CoachPacingReset"] = "CoachPacingReset"
    sessionId: str
    reason: str | None = None
