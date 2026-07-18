"""Immutable-ish internal session records (dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecordedSplit:
    lengthIndex: int
    wallTimestampMs: int
    source: str
    distanceM: float | None
    qualityFlag: str


@dataclass(frozen=True, slots=True)
class VerifiedSplit:
    lengthIndex: int
    verificationSource: str
    verifiedWallTimestampMs: int


@dataclass(frozen=True, slots=True)
class OpenStopPause:
    intervalId: str
    trigger: str
    stopStartedAtMs: int
    confirmedAtMs: int
    trackedAlignmentDistanceM: float
    detectionSource: str
    detectionQuality: str
    alignmentSource: str
    alignmentQuality: str
    stopStartTimeQuality: str
    createdBy: str
    notes: str | None = None
    relatedSetIndex: int | None = None
    relatedRepeatIndex: int | None = None
    relatedLengthIndex: int | None = None


@dataclass(frozen=True, slots=True)
class PendingCoachReset:
    clientCommandId: str
    reason: str | None
    requestedAfterLengthIndex: int = 0
    expectedApplicationWallM: float | None = None
    requestedBy: str = "coach"
