"""Analytics / report contracts.

Two session-end axes are represented:
- active swimming performance (stopped time removed),
- training efficiency (stopped time included).

Duration accounting keeps three durations per length/report:
``activeDurationSec`` + ``stoppedDurationSec`` = ``elapsedDurationSec`` (enforced with a
1e-6 tolerance). Display convention: ``active +stopped`` (e.g. ``20.00 +15.00`` → 35.00
total). If stop timing/alignment is reliable, the length is not discarded (active and
stopped stay separate); if unreliable, the length may be excluded (``exclusionReason``).
"""

from __future__ import annotations

from pydantic import model_validator

from contracts._base import (
    NonNegFloat,
    NonNegInt,
    StrictModel,
    UnitRatio,
    approx_equal,
)
from contracts.enums import (
    AnalyticsExclusionReason,
    SplitQualityFlag,
    StopPauseTrigger,
)


class LengthOutcome(StrictModel):
    lengthIndex: NonNegInt
    targetTimeSec: NonNegFloat
    activeDurationSec: NonNegFloat | None = None
    stoppedDurationSec: NonNegFloat = 0.0
    elapsedDurationSec: NonNegFloat | None = None
    gapSec: float | None = None
    splitQualityFlag: SplitQualityFlag
    included: bool = True
    exclusionReason: AnalyticsExclusionReason | None = None

    @model_validator(mode="after")
    def _duration_accounting(self) -> LengthOutcome:
        if self.activeDurationSec is not None and self.elapsedDurationSec is not None:
            expected = self.activeDurationSec + self.stoppedDurationSec
            if not approx_equal(self.elapsedDurationSec, expected):
                raise ValueError(
                    "elapsedDurationSec must equal activeDurationSec + stoppedDurationSec "
                    f"(got {self.elapsedDurationSec}, expected {expected})"
                )
        return self


class PacingMetrics(StrictModel):
    meanAbsDeviationSec: NonNegFloat
    deviationVariance: NonNegFloat
    negativeSplitAchieved: bool | None = None
    pacingConsistency: UnitRatio
    includedLengths: NonNegInt
    excludedLengths: NonNegInt


class StopPauseSummary(StrictModel):
    count: NonNegInt
    triggerDistribution: dict[StopPauseTrigger, int]
    totalStoppedDurationSec: NonNegFloat
    longestStopDurationSec: NonNegFloat
    affectedLengthIndices: list[NonNegInt]

    @model_validator(mode="after")
    def _stop_summary_consistency(self) -> StopPauseSummary:
        if self.longestStopDurationSec > self.totalStoppedDurationSec + 1e-6:
            raise ValueError("longestStopDurationSec cannot exceed totalStoppedDurationSec")
        if self.count == 0 and (
            self.totalStoppedDurationSec != 0 or self.longestStopDurationSec != 0
        ):
            raise ValueError("count == 0 requires zero stopped durations")
        return self


class SetEfficiencyMetrics(StrictModel):
    setIndex: NonNegInt
    activeSwimmingDurationSec: NonNegFloat
    stoppedDurationSec: NonNegFloat
    elapsedDurationSec: NonNegFloat
    stopCount: NonNegInt
    targetPaceDurationSec: NonNegFloat
    targetPaceAdherenceRatio: UnitRatio
    highIntensityDurationSec: NonNegFloat
    paceContinuityScore: UnitRatio
    paceDeclineStartLength: NonNegInt | None = None
    paceDeclineSlope: float | None = None
    # HR / ML — optional.
    averageHeartRate: NonNegFloat | None = None
    performanceRelatedStopProbability: UnitRatio | None = None

    @model_validator(mode="after")
    def _set_duration_accounting(self) -> SetEfficiencyMetrics:
        expected = self.activeSwimmingDurationSec + self.stoppedDurationSec
        if not approx_equal(self.elapsedDurationSec, expected):
            raise ValueError("elapsedDurationSec must equal active + stopped for the set")
        if self.targetPaceDurationSec > self.activeSwimmingDurationSec + 1e-6:
            raise ValueError("targetPaceDurationSec cannot exceed active swimming duration")
        if self.highIntensityDurationSec > self.activeSwimmingDurationSec + 1e-6:
            raise ValueError("highIntensityDurationSec cannot exceed active swimming duration")
        if self.stopCount == 0 and self.stoppedDurationSec != 0:
            raise ValueError("stopCount == 0 requires zero stoppedDurationSec")
        return self


class TrainingEfficiencyMetrics(StrictModel):
    activeSwimmingDurationSec: NonNegFloat
    totalElapsedDurationSec: NonNegFloat
    totalStoppedDurationSec: NonNegFloat
    stopCount: NonNegInt
    longestStopDurationSec: NonNegFloat
    targetPaceDurationSec: NonNegFloat
    targetPaceAdherenceRatio: UnitRatio
    highIntensityDurationSec: NonNegFloat
    paceContinuityScore: UnitRatio
    paceDeclineStartLength: NonNegInt | None = None
    paceDeclineSlope: float | None = None
    stopBeforeAfterPaceDelta: float | None = None
    # Wearable / HR — optional.
    averageHeartRate: NonNegFloat | None = None
    heartRateTrend: float | None = None
    heartRatePaceRelationship: float | None = None
    setEfficiencyMetrics: list[SetEfficiencyMetrics] = []
    #: ADVISORY ML output only. Never controls the ghost, the clock, or StopPause behaviour.
    performanceRelatedStopProbability: UnitRatio | None = None

    @model_validator(mode="after")
    def _session_duration_accounting(self) -> TrainingEfficiencyMetrics:
        expected = self.activeSwimmingDurationSec + self.totalStoppedDurationSec
        if not approx_equal(self.totalElapsedDurationSec, expected):
            raise ValueError(
                "totalElapsedDurationSec must equal "
                "activeSwimmingDurationSec + totalStoppedDurationSec"
            )
        if self.longestStopDurationSec > self.totalStoppedDurationSec + 1e-6:
            raise ValueError("longestStopDurationSec cannot exceed totalStoppedDurationSec")
        if self.targetPaceDurationSec > self.activeSwimmingDurationSec + 1e-6:
            raise ValueError("targetPaceDurationSec cannot exceed active swimming duration")
        if self.highIntensityDurationSec > self.activeSwimmingDurationSec + 1e-6:
            raise ValueError("highIntensityDurationSec cannot exceed active swimming duration")
        if self.stopCount == 0 and (
            self.totalStoppedDurationSec != 0 or self.longestStopDurationSec != 0
        ):
            raise ValueError("stopCount == 0 requires zero stopped durations")
        return self


class ProfileLegOutcome(StrictModel):
    """Target vs actual for a single profile leg (leg != official wall split)."""

    legIndex: NonNegInt
    fromM: NonNegFloat
    toM: NonNegFloat
    targetDurationSec: NonNegFloat
    actualDurationSec: NonNegFloat | None = None
    deviationSec: float | None = None
    phaseType: str | None = None


class ContinuousCurveReportContext(StrictModel):
    """Optional continuous pace-curve context for the session report (ADR-038 §23).

    Contract-only, forward-compatible fields — Commit 8 does not compute these (that is
    Commit 9 analytics). They never replace the official split reports; they add
    curve-adherence detail for a continuous profile.
    """

    targetContinuousCurveRef: str | None = None
    actualSmoothedCurveRef: str | None = None
    curveDeviationMean: float | None = None
    curveDeviationByPhase: dict[str, float] | None = None
    peakPositiveDeviation: float | None = None
    peakNegativeDeviation: float | None = None
    startCurveAdherence: float | None = None
    turnCurveAdherence: float | None = None
    surfaceCurveAdherence: float | None = None
    finishCurveAdherence: float | None = None
    curveRepresentation: str | None = None
    curveCompilerVersion: str | None = None
    curveReconciliationErrorSec: float | None = None


class PaceProfileReportContext(StrictModel):
    """Optional distance-specific pace-profile context for the session report (§20).

    Natural planned fade (short-distance positive split) and an unexpected collapse are
    separate fields, so a planned fast-start-and-fade is never auto-flagged as bad.
    """

    poolLengthM: int | None = None
    defaultStartMode: str | None = None
    resolvedStartModes: list[str] | None = None
    paceProfileId: str | None = None
    paceProfileVersion: str | None = None
    paceProfileSource: str | None = None
    paceProfileType: str | None = None
    targetTotalTimeSec: NonNegFloat | None = None
    modelConfidence: UnitRatio | None = None
    coachLocked: bool = False
    coachEditedLegIndices: list[NonNegInt] | None = None
    targetLegs: list[ProfileLegOutcome] | None = None
    actualOfficialSplits: list[NonNegFloat] | None = None
    perSplitDeviationSec: list[float] | None = None
    startUnderwaterPhaseSec: NonNegFloat | None = None
    turnEffectSec: float | None = None
    firstVsLastSectionDifferenceSec: float | None = None
    expectedPaceFadeSec: float | None = None
    actualPaceFadeSec: float | None = None
    #: Separate from expected/actual fade: the *unexpected* collapse beyond planned fade.
    unexpectedCollapseDeltaSec: float | None = None
    targetHeartRate: NonNegFloat | None = None
    actualHeartRate: NonNegFloat | None = None
    heartRatePaceRelationship: float | None = None
    strokeRateTrend: float | None = None
    stopPauseDurationsSec: list[NonNegFloat] | None = None
    generalModelVersion: str | None = None
    personalCalibrationVersion: str | None = None
    nextSessionCalibrationSuggestion: str | None = None
    #: Optional continuous pace-curve adherence context (ADR-038); None for 1.0 profiles.
    continuousCurve: ContinuousCurveReportContext | None = None


class SessionReport(StrictModel):
    sessionId: str
    workoutRef: str
    pacingMetrics: PacingMetrics
    trainingEfficiency: TrainingEfficiencyMetrics
    lengthOutcomes: list[LengthOutcome]
    stopPauseSummary: StopPauseSummary
    #: Optional distance-specific pace-profile context (§20). Absent for legacy sessions.
    paceProfileContext: PaceProfileReportContext | None = None
    notes: str | None = None
