# ADR-031 — StopPause and Controlled Ghost Alignment

- **Status:** NEW (Phase 1 scope)
- **Date:** 2026-07-16
- **Supersedes:** the earlier "Ghost Recovery and Re-Anchor Policy (re-anchor only at the
  next valid wall)" design. The general behaviour is now **StopPause**; `MANUAL_INCIDENT`
  survives only as a *trigger*.

## Context / Problem

"Ghost continues under all conditions" collapsed two different realities into one
behaviour: (a) the swimmer tiring and slowing — *this is performance and must be
measured*; (b) an external interruption (collision, lane obstruction, goggle adjustment)
that is not performance but, if the ghost keeps moving, accrues an artificial, meaningless
gap. Pausing the whole session instead destroys set/repetition context. The earlier
re-anchor design also forbade any mid-pool alignment, which felt unnatural: the swimmer and
ghost should be able to wait together where the swimmer actually is.

## Considered options

1. Ghost always continues — pollutes metrics on external interruptions.
2. Session `PAUSED` on interruption — context loss, "session restarted" feel.
3. Teleport the ghost to the swimmer instantly, uncontrolled — confusing, and it makes
   deterministic replay depend on a mid-length position estimate.
4. **Selected:** three explicit behaviours (normal/large pace loss, coach pacing reset,
   StopPause). During a *verified* StopPause the ghost performs **controlled** alignment
   to the swimmer's tracked position (mid-pool allowed), the logical workout clock freezes
   from the moment the stop began, and official length/set/rest accounting is reconciled
   at the next valid wall.

## Decision

The session state machine does not change; the session stays `RUNNING` during a StopPause.
A small ghost operational state (`ACTIVE`, `STOP_PAUSED`) plus a `GhostReference` carries
the alignment. Three behaviours:

- **Normal / large pace loss:** ghost `ACTIVE`, workout clock runs, gap preserved, counts
  toward performance. Never treated or hidden as a StopPause.
- **Coach pacing reset:** a separate command; previous poor performance stays in the
  report; a new pacing reference starts only at the next valid wall; the workout clock is
  **not** frozen. Not a StopPause.
- **StopPause:** triggered manually (`MANUAL_INCIDENT`, `COACH_STOP`) or by exceeding the
  long-stop threshold (default 10s, coach-configurable → `LONG_STOP_THRESHOLD`,
  `SENSOR_STOP`). The logical workout clock freezes retroactively from the stop start; the
  ghost aligns to the swimmer's currently tracked position and waits; on resume both
  continue from the same point on the same target pace; length/set/rest are finalized at
  the next wall.

The system does **not** try to decide *why* the swimmer stopped. It records
`StopDetected{start, end, duration, set/length, sensor snapshot}`, sent live to the coach,
who may annotate it. ML may later produce an advisory `performanceRelatedStopProbability`
only; it never controls the ghost, the clock, or StopPause behaviour.

## Commands

`MarkStopPause{trigger, occurredAtMs, notes?, detectionSource, ...}` ·
`ResolveStopPause{intervalId, endedAtMs, alignmentSource, ...}` ·
`CoachPacingReset{reason?}` (separate; not a StopPause). All carry `clientCommandId` and
are idempotent.

## Events

`StopDetected`, `LongStopConfirmed`, `StopPauseStarted`, `StopPauseResolved`,
`CoachPacingResetRequested`, `CoachPacingResetApplied`. `IncidentStarted` /
`IncidentResolved` are banned as general event names.

## State changes

`ACTIVE --verified StopPause--> STOP_PAUSED --resume/next wall--> ACTIVE`. Normal/large pace
loss produces no ghost transition. Session abort/complete closes any open StopPause interval
(`endedAtMs` written).

## Analytics consequences

Reliable StopPause: the length is not discarded; `activeDurationSec` and
`stoppedDurationSec` are kept separate and stopped time is removed from active pace but
shown explicitly (`active +stopped`). Unreliable stop timing/alignment: the length may be
excluded (`AnalyticsExclusionReason`). Two session-end axes: active swimming performance
(stops removed) and training efficiency (stops included).

## ML consequences

Lengths inside an unreliable StopPause are not ML-label eligible — independent of split
measurement quality. `Split.qualityFlag` is never set to `INVALID` because of a StopPause.

## Reversibility

MEDIUM. Ghost state and events are additive; reverting means ignoring the new event types.
Because the analytics-exclusion semantics reinterpret past reports if reverted, this is
locked in Phase 1 at the contract level.

## Validation tests

Ghost operational-state transitions; workout-clock freeze/resume; mid-pool alignment
allowed only when verified; reconciliation deferred to the next wall; idempotent
StopPause/resolve; split quality unaffected by StopPause; replay determinism.
