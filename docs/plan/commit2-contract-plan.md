# Commit 2 — Contract Plani (guncellenmis)

Tum sozlesmeler `src/contracts/` altinda pydantic v2; JSON Schema `swimtools.gen_schemas` ile uretilir.
`swimcore` bunlari import eder; `contracts.external_data` HARIC (ADR-032, import-linter forbidden).

## contracts/enums.py
Stroke · PoolLengthM(25|50) · PaceMode(even_pace|controlled_start|progressive|negative_split_part) ·
AdaptationMode(off|suggest_only|bounded_auto) · AdaptationSource(rule_based|ml) · RestType(none|fixed|interval)
SplitSource(BUTTON|COACH_TAP|TOUCHPAD|WEARABLE|SIMULATED) · SplitQualityFlag(VERIFIED_HIGH|RELIABLE|
MANUAL_UNVERIFIED|ESTIMATED|INVALID) · **StopTrigger(MANUAL_INCIDENT|LONG_STOP_THRESHOLD|COACH_STOP|
SENSOR_STOP)** · **StopDetectionSource(COACH|SENSOR|ESTIMATOR|THRESHOLD)** · **StopSignalQuality(HIGH|
MEDIUM|LOW|UNKNOWN)** · **GhostAlignmentSource(SENSOR|COACH|ESTIMATE|NONE)** · GhostTimingState(ACTIVE|
STOP_PAUSED) · AnalyticsExclusionReason(STOP_TIME_UNRELIABLE) · ReasonCode(...)

## contracts/workout.py
WorkoutTemplateVersion · RepeatBlock · PaceSegment(targetPaceSecPer100M, endPaceSecPer100M?) ·
RestPolicy · AdaptationPolicy(fastestAllowedPaceSecPer100M, slowestAllowedPaceSecPer100M,
maxChangePercentPerLength, minModelConfidence, mode, adaptationSource) · FeedbackPolicy · GhostSource.
Yon kurali: fastestAllowed <= target <= slowestAllowed.

## contracts/pacing.py
PaceTarget(appliedPaceSecPer100M, origin) · GhostState(distanceM, speedMps, timingState) ·
SwimmerState · ControlDecision(suggestedPaceSecPer100M?, appliedPaceSecPer100M?, decision, reasonCode) ·
ReasonCode enum.

## contracts/stop_pause.py   (ADR-031 — YENI, "incident" degil)
StopTrigger · StopDetection{stopStartedAtMs, detectionSource, detectionQuality, stopStartTimeQuality} ·
StopPause{stopPauseId, trigger, stopStartedAtMs, atLengthIndex, alignedGhostDistanceM?, alignmentSource,
alignmentQuality, resumedAtMs?, stoppedDurationSec?, reconciledAtWallLengthIndex?, affectedLengthIndices[],
lengthAnalyzable, analyticsEligible, mlLabelEligible} · CoachPacingReset{resetId, effectiveBoundaryLengthIndex, reason}

## contracts/splits.py
Split{sessionId, lengthIndex, wallTimestampMs, source, qualityFlag, mlEligible, researchEligible,
verificationRef?} · SplitVerification{verificationSource, verifiedWallTimestampMs, manualErrorMs, verifiedBy}

## contracts/durations.py   (YENI — uc sure alani)
DurationAccounting{activeDurationSec, stoppedDurationSec, elapsedDurationSec}
Degismez: elapsedDurationSec == activeDurationSec + stoppedDurationSec.

## contracts/commands.py
CreateSession · Arm/Start/Pause/Resume/Abort/Complete · RecordSplit · VerifySplit · ApplyCoachPaceTarget ·
**MarkStopPause(trigger, occurredAtMs?, notes?)** · **ResolveStopPause(resumedAtMs)** ·
**CoachPacingReset(reason)**. Hepsi clientCommandId(uuid4) tasir.

## contracts/events.py
EventEnvelope{eventId(uuid4), seq, sessionId, type, tsMs, wallTs?, schemaVersion, producer,
clientCommandId?, causationId?, payload}. Tipler: docs/domain/event-catalog.md.
StopPause event'leri: StopDetected, LongStopConfirmed, StopPauseStarted, StopPauseResolved, CoachPacingReset.

## contracts/analytics.py
LengthOutcome{lengthIndex, targetTimeSec, activeDurationSec?, stoppedDurationSec?, elapsedDurationSec?,
gapSec?, splitQualityFlag, included, exclusionReason?} · PacingMetrics · StopSummary{count, triggerDist,
totalStoppedDurationSec, longestStopDurationSec, affectedLengthIndices[]} · SessionReport.

## contracts/efficiency.py   (YENI — TrainingEfficiencyMetrics; nabiz/wearable alanlari Faz 1'de optional)
TrainingEfficiencyMetrics{
  activeSwimmingDurationSec, totalElapsedDurationSec, totalStoppedDurationSec, stopCount,
  longestStopDurationSec, targetPaceDurationSec, targetPaceAdherenceRatio, highIntensityDurationSec,
  paceContinuityScore, paceDeclineStartLength?, paceDeclineSlope?, stopBeforeAfterPaceDelta?,
  averageHeartRate?, heartRateTrend?, heartRatePaceRelationship?, setEfficiencyMetrics[],
  performanceRelatedStopProbability?   # ML yardimci ciktisi; ghost/clock/stop'u KONTROL ETMEZ
}

## contracts/external_data.py   (PLAN-LEVEL; swimcore import EDEMEZ)
ExternalDataDomain · DataSourceRegistryEntry(18 alan) · ExternalRecordProvenance · NormalizedSwimmingRecord.

## Uretilen semalar
contracts/schemas/{workout-1.0.json, event-envelope-1.0.json, session-report-1.0.json,
training-efficiency-1.0.json}. Golden: examples/valid/*, examples/invalid/*.
