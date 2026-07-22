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

## Persistence: EventBatchRecord (Commit 7, ADR-037)

Bir komutun TUM eventleri tek `EventBatchRecord` = tek canonical JSONL satiridir
(recordVersion 1.0; uretilen sema: `event-batch-record-1.0.json`, elle duzenlenmez):
```
EventBatchRecord {recordType:"EVENT_BATCH", recordVersion:"1.0", sessionId,
                  clientCommandId, firstSeq, lastSeq, eventCount, events[]}
```
Kurallar: bos batch yok; seq kesintisiz; tek session + tek clientCommandId; ts azalmaz;
eventId benzersiz; NaN/Infinity codec'te reddedilir. Canonical encoding: UTF-8, BOM yok,
sort_keys, compact separators, tam bir `\n`.

## SessionRecovered (Commit 7, ADR-037)

```
SessionRecovered {sessionId, recoveredEventCount, lastRecoveredSeq,
                  tailTruncated, truncatedByteCount, recoveryReason}
```
Journal okunurken OTOMATIK uretilmez ve loga otomatik append edilmez; yalnizca
`persistence.recovery.build_session_recovered_event` (enjekte Clock + EventIdGenerator) ile
uretilir. Replay'de lifecycle'i degistirmez; sadece `recoveryCount`'u artirir.


## Commit 8 correction — payload additions (backward compatible)

All fields below are optional with safe defaults; existing journals parse unchanged.

**`SessionCreated`**
- `selectedProfileTargetTotalTimeSec`, `selectedCurveRepresentation`,
  `selectedCurveCompilerVersion` — the selected profile's timeline metadata, so historical
  replay carries the same profile state axes as the live aggregate.

**`CoachPacingResetRequested`**
- `replacementPaceProfileSource`, `replacementPaceProfileType`,
  `replacementProfileCoachLocked`, `replacementCurveRepresentation`,
  `replacementCurveCompilerVersion`.

**`CoachPacingResetApplied`**
- the same five fields plus `replacementAppliedPaceSecPer100M` — the replacement timeline's
  current target just after the application wall.

Rule: when a continuous-curve replacement is applied, **every** selected-profile field is
adopted from the replacement — an earlier `COACH_AUTHORED` source must not survive a
`COACH_APPROVED_MODEL` replacement, and a coach-locked replacement must read as locked in
both live and replay state.
