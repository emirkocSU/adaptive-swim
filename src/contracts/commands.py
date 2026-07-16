"""Command contracts.

Every command carries ``clientCommandId`` for idempotency. ``CoachPacingReset`` is NOT a
StopPause: it does not erase previous poor performance; it only starts a new pacing
reference at the next valid wall boundary.
"""

from __future__ import annotations

from typing import Literal

from contracts._base import NonEmptyStr, NonNegInt, PaceValue, StrictModel
from contracts.enums import (
    AlignmentSource,
    SplitSource,
    StopDetectionSource,
    StopPauseTrigger,
    VerificationSource,
)


class Command(StrictModel):
    """Base command; ``commandType`` is a discriminating literal on each subclass."""

    clientCommandId: NonEmptyStr


class CreateSession(Command):
    commandType: Literal["CreateSession"] = "CreateSession"
    workoutRef: str


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
    lengthIndex: NonNegInt
    wallTimestampMs: NonNegInt
    source: SplitSource


class VerifySplit(Command):
    commandType: Literal["VerifySplit"] = "VerifySplit"
    sessionId: str
    lengthIndex: int
    verificationSource: VerificationSource
    verifiedWallTimestampMs: NonNegInt


class MarkStopPause(Command):
    commandType: Literal["MarkStopPause"] = "MarkStopPause"
    sessionId: str
    trigger: StopPauseTrigger
    occurredAtMs: NonNegInt
    detectionSource: StopDetectionSource
    notes: str | None = None


class ResolveStopPause(Command):
    commandType: Literal["ResolveStopPause"] = "ResolveStopPause"
    sessionId: str
    intervalId: str
    endedAtMs: NonNegInt
    alignmentSource: AlignmentSource = AlignmentSource.WALL_RECONCILIATION


class ApplyCoachPaceTarget(Command):
    commandType: Literal["ApplyCoachPaceTarget"] = "ApplyCoachPaceTarget"
    sessionId: str
    appliedPaceSecPer100M: PaceValue


class CoachPacingReset(Command):
    commandType: Literal["CoachPacingReset"] = "CoachPacingReset"
    sessionId: str
    reason: str | None = None
