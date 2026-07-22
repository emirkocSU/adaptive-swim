# State Machine'ler

## Session (DEGISMEZ — StopPause session state'ini degistirmez)
```
DRAFT -> VALIDATED -> ASSIGNED -> DEVICE_READY -> ARMED -> RUNNING
RUNNING <-> PAUSED (yalnizca koc komutu)
RUNNING -> COMPLETED | ABORTED | DEGRADED_MODE
```
StopPause sirasinda session **RUNNING kalir**. `SessionPaused` (koc, tum seansi dondurur) ile StopPause
**karistirilmaz**.

## Ghost / Workout timing sub-state (ADR-031)
```
ACTIVE
  |-- kisa durma (< longStopThresholdSec) ve devam    -> ACTIVE (saat durmaz; Durum A)
  |-- MarkStopPause / durma >= threshold (guvenilir)   -> STOP_PAUSED (Durum C)
  |-- CoachPacingReset                                 -> ACTIVE (Durum B; referans sonraki duvarda)
STOP_PAUSED
  |-- ResolveStopPause / yuzucu devam etti             -> ACTIVE (saat kaldigi yerden)
  |-- SessionCompleted / SessionAborted                -> terminal cleanup
```
State verisi: `longStopThresholdSec`, `stopStartedAtMs?`, `openStopPauseId?`, `cumulativeStoppedMs`,
`alignedGhostDistanceM?`. STOP_PAUSED iken workout/ghost/pace/rest saatleri donuktur; real clock akar.

## Swimmer (pacing-related; ghost'u ETKILEMEZ)
```
AT_WALL -> PUSH_OFF -> SWIMMING -> APPROACHING_WALL -> AT_WALL
SWIMMING -> POSSIBLE_STOP -> STOPPED -> RESUMED
```
Bu gecisler ghost'u durdurmaz; ghost Durum A'da ilerler. Yalnizca StopPause trigger'i dogrulaninca
(Durum C) ghost durur ve kontrollu hizalanir.

## Historical replay (Commit 7, ADR-037)

Replay, event akisini saf bir fold ile `HistoricalSessionState`'e indirger ve **ayni**
lifecycle gecis tablosunu (`swimcore/session/transitions.py`) yeniden kullanir — ikinci bir
gecis tablosu yazmak yasaktir. Terminal durumdan sonra normal domain event reddedilir
(`SessionRecovered` isaretleyicisi haric; o lifecycle'i degistirmez). StopPause lifecycle
state'i DEGILDIR: replay sirasinda da session RUNNING kalir; acik lifecycle pause + acik
StopPause ayni anda gorulurse stream corruption sayilir. Sure eksenleri ayridir:
`elapsed = active + stopped`, `wall = elapsed + lifecyclePaused`.


## Commit 8 correction — behaviours pinned by the required scenarios

The eight required simulator scenarios are the executable statement of these state rules:

| Scenario | State-machine rule pinned |
|---|---|
| `normal-pace-loss` | a growing pace gap is not an incident: no StopPause, the ghost and ActiveClock keep running |
| `long-stop-mid-length` | the retroactive stop start (payload `startedAtMs`) precedes confirmation; the tracked mid-pool alignment never becomes official distance; exactly one wall reconciliation follows the resolve |
| `manual-stop-at-verified-wall` | a manual stop aligned at an official wall reconciles at that wall; a StopPause is never a lifecycle pause |
| `duplicate-stop-mark` | command idempotency: the same clientCommandId with identical content yields zero new events and zero new journal batches |
| `stop-during-planned-rest` | planned rest is a schedule-level concept; it creates no StopPause, adds no stopped duration and no synthetic lifecycle state |
| `unreliable-position-time` | low position confidence is a display axis only; official distance and completed lengths follow pool geometry and verified walls |
| `complete-while-stop-paused` | `CompleteSession` is rejected while a StopPause is open and mutates nothing; it succeeds after the resolve and the final official wall |
| `coach-continuous-curve-reset` | a mid-length reset request applies only at the next official wall, swaps the full profile metadata, is not a StopPause and preserves split history |

## Analytics boundary

Report construction has no state-machine transition. It observes the replayed lifecycle,
StopPause and coach-reset states at a fixed event horizon. Planned rest, lifecycle pause,
StopPause and safe-wall coach reset remain separate axes in all report calculations.


## Phase 1 closure — state rules proven end to end (ADR-041)

The vertical-slice cases are the executable statement of the Phase 1 state rules:

| Case | Rule proven through the whole chain |
|---|---|
| `normal-continuous-completion` | a clean session completes; official distance equals the plan; no StopPause |
| `legacy-profile-compatibility` | the legacy constant-leg path still runs without migration |
| `migrated-profile-equivalence` | a 1.0 → 1.1 migration preserves the compiled target function |
| `long-stop-and-reconciliation` | retroactive freeze, mid-pool estimate is not official distance, exactly one wall reconciliation |
| `coach-profile-reset` | mid-length request, next-wall application, full metadata swap, past split provenance preserved, no stopped time |
| `complete-while-stop-paused` | a rejected completion mutates neither aggregate, sequence nor journal; it succeeds after resolve |
| `duplicate-command-durability` | an identical retry yields no second event, no duplicate line, no sequence gap |
| `unreliable-observation-report` | low confidence never changes official distance and never fabricates a curve |
| `dataset-evidence-provenance` | dataset evidence travels as provenance only, never as measured velocity |
| `fifty-metre-pool-official-distance` | a 50 m course starts at 0 m and its first length is exactly 50 m |
| `normal-pace-loss`, `manual-stop-at-verified-wall`, `stop-during-planned-rest` | the remaining required failure scenarios, now also producing reports |
