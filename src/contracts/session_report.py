"""Deterministic SessionReport 1.1 contracts (ADR-040).

The append-only event journal remains authoritative.  A report is a derived artifact built
from historical replay plus explicitly supplied planning/observation inputs.  Missing data
is represented by metric status and ``None`` values; it is never fabricated as zero.

``contracts.analytics.SessionReport`` remains the immutable 1.0 contract.  This module adds
1.1 without changing the committed 1.0 schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import model_validator

from contracts._base import (
    FiniteFloat,
    NonEmptyStr,
    NonNegFiniteFloat,
    NonNegInt,
    StrictModel,
    UnitFiniteRatio,
)


class MetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LOW_QUALITY = "LOW_QUALITY"
    MISSING_TARGET = "MISSING_TARGET"
    UNSUPPORTED_CONTEXT = "UNSUPPORTED_CONTEXT"
    EXCLUDED_BY_POLICY = "EXCLUDED_BY_POLICY"


class AheadBehindStatus(StrEnum):
    AHEAD = "AHEAD"
    ON_TARGET = "ON_TARGET"
    BEHIND = "BEHIND"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class PacingShapeClass(StrEnum):
    EVEN = "EVEN"
    NEGATIVE = "NEGATIVE"
    POSITIVE_FADE = "POSITIVE_FADE"
    PROGRESSIVE = "PROGRESSIVE"
    IRREGULAR = "IRREGULAR"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ReportCompletionStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class SessionSummary(StrictModel):
    lifecycleState: NonEmptyStr
    completionStatus: ReportCompletionStatus
    terminal: bool
    recordedSplitCount: NonNegInt
    verifiedSplitCount: NonNegInt
    stopPauseOpen: bool
    pendingCoachReset: bool


class TimingSummary(StrictModel):
    status: MetricStatus
    wallDurationMs: NonNegInt | None = None
    activeDurationMs: NonNegInt | None = None
    stoppedDurationMs: NonNegInt | None = None
    lifecyclePausedDurationMs: NonNegInt | None = None
    elapsedDurationMs: NonNegInt | None = None
    sessionStartMs: NonNegInt | None = None
    sessionEndMs: NonNegInt | None = None

    @model_validator(mode="after")
    def _duration_identities(self) -> TimingSummary:
        if self.status is MetricStatus.AVAILABLE:
            required = (
                self.wallDurationMs,
                self.activeDurationMs,
                self.stoppedDurationMs,
                self.lifecyclePausedDurationMs,
                self.elapsedDurationMs,
                self.sessionStartMs,
            )
            if any(value is None for value in required):
                raise ValueError("AVAILABLE timing summary requires all non-terminal timing fields")
            assert self.wallDurationMs is not None
            assert self.activeDurationMs is not None
            assert self.stoppedDurationMs is not None
            assert self.lifecyclePausedDurationMs is not None
            assert self.elapsedDurationMs is not None
            if self.elapsedDurationMs != self.activeDurationMs + self.stoppedDurationMs:
                raise ValueError(
                    "elapsedDurationMs must equal activeDurationMs + stoppedDurationMs"
                )
            if self.wallDurationMs != self.elapsedDurationMs + self.lifecyclePausedDurationMs:
                raise ValueError(
                    "wallDurationMs must equal elapsedDurationMs + lifecyclePausedDurationMs"
                )
        return self


class DistanceSummary(StrictModel):
    status: MetricStatus
    plannedDistanceM: NonNegFiniteFloat | None = None
    officialCompletedDistanceM: NonNegFiniteFloat | None = None
    completedLengthCount: NonNegInt
    poolLengthM: NonNegInt | None = None
    completionRatio: UnitFiniteRatio | None = None
    officialSplitCount: NonNegInt
    lastVerifiedWallM: NonNegFiniteFloat | None = None
    partial: bool


class PaceProfileContextV1_1(StrictModel):
    status: MetricStatus
    paceProfileId: str | None = None
    paceProfileVersion: str | None = None
    paceProfileSource: str | None = None
    paceProfileType: str | None = None
    coachLocked: bool | None = None
    targetTotalTimeSec: NonNegFiniteFloat | None = None
    targetSplitTimesSec: tuple[NonNegFiniteFloat, ...] | None = None
    predictedSplitTimesSec: tuple[NonNegFiniteFloat, ...] | None = None
    predictedNextSplitTimeSec: NonNegFiniteFloat | None = None
    predictedNextRepeatTimeSec: NonNegFiniteFloat | None = None
    uncertaintyP10: FiniteFloat | None = None
    uncertaintyP50: FiniteFloat | None = None
    uncertaintyP90: FiniteFloat | None = None


class SplitPerformance(StrictModel):
    splitIndex: NonNegInt
    fromM: NonNegFiniteFloat
    toM: NonNegFiniteFloat
    distanceM: NonNegFiniteFloat
    actualStartTimeMs: NonNegInt
    actualEndTimeMs: NonNegInt
    elapsedDurationSec: NonNegFiniteFloat
    stoppedDurationSec: NonNegFiniteFloat
    lifecyclePausedDurationSec: NonNegFiniteFloat
    actualDurationSec: NonNegFiniteFloat
    actualCumulativeTimeSec: NonNegFiniteFloat
    actualSpeedMps: NonNegFiniteFloat | None = None
    targetDurationSec: NonNegFiniteFloat | None = None
    targetCumulativeTimeSec: NonNegFiniteFloat | None = None
    targetSpeedMps: NonNegFiniteFloat | None = None
    durationDeltaSec: FiniteFloat | None = None
    durationDeltaPct: FiniteFloat | None = None
    cumulativeDeltaSec: FiniteFloat | None = None
    speedDeltaMps: FiniteFloat | None = None
    aheadBehindStatus: AheadBehindStatus
    splitSource: NonEmptyStr
    qualityFlags: tuple[NonEmptyStr, ...]
    excludedFromAggregateMetrics: bool
    exclusionReasons: tuple[NonEmptyStr, ...] = ()
    profileId: str | None = None
    profileVersion: str | None = None
    profileSource: str | None = None
    profileType: str | None = None
    curvePhaseTypes: tuple[NonEmptyStr, ...] = ()
    targetStatus: MetricStatus

    @model_validator(mode="after")
    def _span_and_duration(self) -> SplitPerformance:
        if self.toM <= self.fromM:
            raise ValueError("split toM must be greater than fromM")
        if abs(self.distanceM - (self.toM - self.fromM)) > 1e-6:
            raise ValueError("distanceM must equal toM - fromM")
        if self.actualEndTimeMs < self.actualStartTimeMs:
            raise ValueError("actualEndTimeMs must be >= actualStartTimeMs")
        total = self.actualDurationSec + self.stoppedDurationSec + self.lifecyclePausedDurationSec
        if abs(self.elapsedDurationSec - total) > 1e-6:
            raise ValueError(
                "elapsedDurationSec must equal actual + stopped + lifecycle paused durations"
            )
        if self.targetStatus is MetricStatus.AVAILABLE and self.targetDurationSec is None:
            raise ValueError("AVAILABLE targetStatus requires targetDurationSec")
        return self


class SplitAggregateMetrics(StrictModel):
    status: MetricStatus
    eligibleSplitCount: NonNegInt
    excludedSplitCount: NonNegInt
    meanAbsoluteSplitErrorSec: NonNegFiniteFloat | None = None
    meanAbsoluteSplitPercentageError: NonNegFiniteFloat | None = None
    rootMeanSquaredSplitErrorSec: NonNegFiniteFloat | None = None
    maximumPositiveSplitErrorSec: NonNegFiniteFloat | None = None
    maximumNegativeSplitErrorSec: FiniteFloat | None = None
    targetPaceAdherenceRatio: UnitFiniteRatio | None = None
    onTargetSplitRatio: UnitFiniteRatio | None = None
    firstHalfTimeSec: NonNegFiniteFloat | None = None
    secondHalfTimeSec: NonNegFiniteFloat | None = None
    firstHalfSecondHalfDeltaSec: FiniteFloat | None = None
    firstHalfSecondHalfDeltaPct: FiniteFloat | None = None


class SplitAnalysis(StrictModel):
    status: MetricStatus
    splits: tuple[SplitPerformance, ...]
    aggregate: SplitAggregateMetrics


class PaceFadeAnalysis(StrictModel):
    status: MetricStatus
    expectedPaceFadePct: FiniteFloat | None = None
    actualPaceFadePct: FiniteFloat | None = None
    paceDeclineStartSplit: NonNegInt | None = None
    paceDeclineSlope: FiniteFloat | None = None
    unexpectedCollapse: bool | None = None
    unexpectedCollapseDeltaPct: FiniteFloat | None = None


class PacingAnalysis(StrictModel):
    status: MetricStatus
    targetPacingShape: PacingShapeClass
    actualPacingShape: PacingShapeClass
    fade: PaceFadeAnalysis
    eligibleSpeedSeriesMps: tuple[NonNegFiniteFloat, ...] = ()
    warningCodes: tuple[NonEmptyStr, ...] = ()


class PhaseCurveDeviation(StrictModel):
    phaseType: NonEmptyStr
    status: MetricStatus
    observationCount: NonNegInt
    coverageRatio: UnitFiniteRatio
    meanDistanceDeviationM: FiniteFloat | None = None
    meanAbsoluteDistanceDeviationM: NonNegFiniteFloat | None = None
    rmsDistanceDeviationM: NonNegFiniteFloat | None = None


class ContinuousCurveAnalysis(StrictModel):
    available: bool
    status: MetricStatus
    reason: str | None = None
    targetContinuousCurveRef: str | None = None
    actualSmoothedCurveRef: str | None = None
    curveDeviationMean: FiniteFloat | None = None
    curveDeviationMeanAbsolute: NonNegFiniteFloat | None = None
    curveDeviationRms: NonNegFiniteFloat | None = None
    curveDeviationByPhase: tuple[PhaseCurveDeviation, ...] = ()
    peakPositiveDeviation: FiniteFloat | None = None
    peakNegativeDeviation: FiniteFloat | None = None
    startCurveAdherence: UnitFiniteRatio | None = None
    turnCurveAdherence: UnitFiniteRatio | None = None
    surfaceCurveAdherence: UnitFiniteRatio | None = None
    finishCurveAdherence: UnitFiniteRatio | None = None
    curveCoverageRatio: UnitFiniteRatio
    observationCount: NonNegInt
    curveRepresentation: str | None = None
    curveCompilerVersion: str | None = None
    curveReconciliationErrorSec: NonNegFiniteFloat | None = None


class StopPauseIntervalSummary(StrictModel):
    stopIndex: NonNegInt
    intervalId: NonEmptyStr
    trigger: NonEmptyStr
    startedAtMs: NonNegInt
    confirmedAtMs: NonNegInt | None = None
    resolvedAtMs: NonNegInt | None = None
    durationMs: NonNegInt | None = None
    alignmentSource: NonEmptyStr | None = None
    estimatedAlignmentDistanceM: NonNegFiniteFloat | None = None
    officialDistanceBeforeM: NonNegFiniteFloat | None = None
    officialDistanceAfterM: NonNegFiniteFloat | None = None
    reconciledAtWallM: NonNegFiniteFloat | None = None
    retroactiveFreezeMs: NonNegInt
    detectionSource: NonEmptyStr
    stopStartTimeQuality: NonEmptyStr | None = None
    alignmentQuality: NonEmptyStr | None = None
    resolved: bool
    wallReconciliationPendingAtResolve: bool
    wallReconciliationCompleted: bool
    wallReconciliationPendingAtReport: bool

    @model_validator(mode="after")
    def _reconciliation_consistency(self) -> StopPauseIntervalSummary:
        if self.wallReconciliationCompleted and self.wallReconciliationPendingAtReport:
            raise ValueError("wall reconciliation cannot be completed and pending")
        if self.wallReconciliationCompleted != (self.reconciledAtWallM is not None):
            raise ValueError(
                "reconciledAtWallM must be present exactly when reconciliation completed"
            )
        if self.wallReconciliationPendingAtReport and not self.wallReconciliationPendingAtResolve:
            raise ValueError("report-time pending reconciliation must have been pending at resolve")
        return self


class StopPauseAnalysis(StrictModel):
    status: MetricStatus
    stopPauseCount: NonNegInt
    totalStoppedDurationMs: NonNegInt
    longestStopDurationMs: NonNegInt
    meanStopDurationMs: NonNegFiniteFloat | None = None
    resolvedStopCount: NonNegInt
    unresolvedStopCount: NonNegInt
    retroactiveStopCount: NonNegInt
    manualStopCount: NonNegInt
    automaticStopCount: NonNegInt
    temporaryAlignmentCount: NonNegInt
    wallReconciliationCount: NonNegInt
    pendingWallReconciliationCount: NonNegInt
    intervals: tuple[StopPauseIntervalSummary, ...]

    @model_validator(mode="after")
    def _stop_consistency(self) -> StopPauseAnalysis:
        known_total = sum(interval.durationMs or 0 for interval in self.intervals)
        if self.unresolvedStopCount == 0 and known_total != self.totalStoppedDurationMs:
            raise ValueError("resolved StopPause interval durations must sum to total")
        if self.longestStopDurationMs > self.totalStoppedDurationMs:
            raise ValueError("longest stop cannot exceed total stopped duration")
        completed = sum(1 for interval in self.intervals if interval.wallReconciliationCompleted)
        pending = sum(
            1 for interval in self.intervals if interval.wallReconciliationPendingAtReport
        )
        if self.wallReconciliationCount != completed:
            raise ValueError("wallReconciliationCount must equal completed reconciliations")
        if self.pendingWallReconciliationCount != pending:
            raise ValueError(
                "pendingWallReconciliationCount must equal report-time pending reconciliations"
            )
        return self


class CoachResetSummary(StrictModel):
    resetIndex: NonNegInt
    requestedAtMs: NonNegInt
    appliedAtMs: NonNegInt | None = None
    appliedWallDistanceM: NonNegFiniteFloat | None = None
    previousProfileId: str | None = None
    previousProfileVersion: str | None = None
    previousProfileSource: str | None = None
    previousProfileType: str | None = None
    previousCoachLocked: bool | None = None
    replacementProfileId: str | None = None
    replacementProfileVersion: str | None = None
    replacementProfileSource: str | None = None
    replacementProfileType: str | None = None
    replacementCoachLocked: bool | None = None


class CoachResetAnalysis(StrictModel):
    status: MetricStatus
    coachResetRequestedCount: NonNegInt
    coachResetAppliedCount: NonNegInt
    pendingCoachResetCount: NonNegInt
    safeWallApplicationCount: NonNegInt
    resets: tuple[CoachResetSummary, ...]


class HeartRateAnalysis(StrictModel):
    available: bool
    status: MetricStatus
    sampleCount: NonNegInt
    averageHeartRateBpm: NonNegFiniteFloat | None = None
    minimumHeartRateBpm: NonNegFiniteFloat | None = None
    maximumHeartRateBpm: NonNegFiniteFloat | None = None
    heartRateTrendBpmPerMinute: FiniteFloat | None = None
    heartRatePaceRelationship: FiniteFloat | None = None
    coverageRatio: UnitFiniteRatio
    qualityFlags: tuple[NonEmptyStr, ...] = ()


class StrokeAnalysis(StrictModel):
    available: bool
    status: MetricStatus
    sampleCount: NonNegInt
    averageStrokeRateCyclesPerMin: NonNegFiniteFloat | None = None
    strokeRateTrend: FiniteFloat | None = None
    averageStrokeLengthMPerCycle: NonNegFiniteFloat | None = None
    averageStrokeIndex: NonNegFiniteFloat | None = None
    strokeCountTotal: NonNegFiniteFloat | None = None
    coverageRatio: UnitFiniteRatio
    qualityFlags: tuple[NonEmptyStr, ...] = ()


class SensorAnalysis(StrictModel):
    heartRate: HeartRateAnalysis
    stroke: StrokeAnalysis


class MetricAvailability(StrictModel):
    metric: NonEmptyStr
    status: MetricStatus
    reason: str | None = None


class ReportDataQuality(StrictModel):
    eventStreamComplete: bool
    replayValid: bool
    officialDistanceComplete: bool
    targetProfileAvailable: bool
    continuousObservationCoverage: UnitFiniteRatio
    sensorCoverage: UnitFiniteRatio
    excludedSplitCount: NonNegInt
    warningCodes: tuple[NonEmptyStr, ...] = ()
    metricAvailability: tuple[MetricAvailability, ...] = ()


class ReportProvenance(StrictModel):
    analyticsVersion: NonEmptyStr
    reportBuilderVersion: NonEmptyStr
    reportSchemaVersion: Literal["1.1"]
    eventFirstSeq: NonNegInt
    eventLastSeq: NonNegInt
    eventCount: NonNegInt
    eventDigestSha256: NonEmptyStr
    workoutDigestSha256: NonEmptyStr
    initialPaceProfileDigestSha256: NonEmptyStr | None = None
    compiledTimelineDigestSha256: NonEmptyStr | None = None
    profileRegistryDigestSha256: NonEmptyStr
    observationDigestSha256: NonEmptyStr
    sensorObservationDigestSha256: NonEmptyStr
    analyticsPolicyDigestSha256: NonEmptyStr
    reportInputDigestSha256: NonEmptyStr
    workoutSchemaVersion: str | None = None
    paceProfileSchemaVersion: str | None = None
    paceProfileId: str | None = None
    paceProfileVersion: str | None = None
    paceProfileSource: str | None = None
    paceProfileType: str | None = None
    curveRepresentation: str | None = None
    curveCompilerVersion: str | None = None
    datasetEvidenceAssetIds: tuple[NonEmptyStr, ...] = ()
    curveOrigin: str | None = None
    curveEvidenceLevel: str | None = None
    visualShapeSource: str | None = None
    continuousCurveGroundTruth: bool | None = None
    simulatorSynthetic: bool
    simulationRunId: str | None = None
    adherenceToleranceSec: NonNegFiniteFloat
    onTargetTolerancePct: NonNegFiniteFloat
    declineMinimumConsecutiveSplits: NonNegInt
    declineMinimumPct: NonNegFiniteFloat


class SessionReportV1_1(StrictModel):
    schemaVersion: Literal["1.1"] = "1.1"
    reportId: NonEmptyStr
    reportVersion: NonEmptyStr
    sessionId: NonEmptyStr
    workoutId: NonEmptyStr
    reportGeneratedAtMs: NonNegInt
    createdFromLastSeq: NonNegInt
    sessionSummary: SessionSummary
    timingSummary: TimingSummary
    distanceSummary: DistanceSummary
    paceProfileContext: PaceProfileContextV1_1
    splitAnalysis: SplitAnalysis
    pacingAnalysis: PacingAnalysis
    continuousCurveAnalysis: ContinuousCurveAnalysis
    stopPauseAnalysis: StopPauseAnalysis
    coachResetAnalysis: CoachResetAnalysis
    sensorAnalysis: SensorAnalysis
    dataQuality: ReportDataQuality
    provenance: ReportProvenance
    notes: str | None = None


SessionReportVersion = SessionReportV1_1
