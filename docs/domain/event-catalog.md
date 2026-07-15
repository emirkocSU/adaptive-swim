# Event Katalogu

Zarf: `{eventId(uuid4), seq(session ici monotonik), sessionId, type, tsMs(monotonic),
wallTs?, schemaVersion, producer, clientCommandId?, causationId?, payload}`.
Kimlik ve zaman ENJEKTE edilir (ADR-033); ULID kullanilmaz.

## Faz 1 event tipleri
WorkoutValidated · SessionCreated/Armed/Started/Paused/Resumed/Completed/Aborted · LengthStarted ·
SplitRecorded · SplitVerified · SwimmerStopped/Resumed (pacing-related; ghost'u etkilemez) ·
PaceTargetChanged · ControlDecisionMade · **StopDetected** · **LongStopConfirmed** ·
**StopPauseStarted** · **StopPauseResolved** · **CoachPacingReset** · SessionRecovered (replay).

## StopPause payload'lari (ADR-031)
```
StopDetected      {stopStartedAtMs, setIndex, lengthIndex, sensorSnapshot?,
                   detectionSource: COACH|SENSOR|ESTIMATOR|THRESHOLD,
                   detectionQuality: HIGH|MEDIUM|LOW|UNKNOWN,
                   stopStartTimeQuality: HIGH|MEDIUM|LOW|UNKNOWN}
LongStopConfirmed {stopStartedAtMs, confirmedAtMs, trigger, longStopThresholdSec}
StopPauseStarted  {stopPauseId, trigger, stopStartedAtMs, atLengthIndex,
                   alignedGhostDistanceM?, alignmentSource: SENSOR|COACH|ESTIMATE|NONE,
                   alignmentQuality: HIGH|MEDIUM|LOW|UNKNOWN, notes?}
StopPauseResolved {stopPauseId, resumedAtMs, stoppedDurationSec,
                   reconciledAtWallLengthIndex?, affectedLengthIndices[],
                   lengthAnalyzable, analyticsEligible, mlLabelEligible}
CoachPacingReset  {resetId, requestedAtMs, effectiveBoundaryLengthIndex, reason}
```
StopTrigger: MANUAL_INCIDENT | LONG_STOP_THRESHOLD | COACH_STOP | SENSOR_STOP.
Idempotency: her komut `clientCommandId` tasir; tekrar ikinci pause/saat-dusumu/reset uretmez.
