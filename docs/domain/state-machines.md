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
