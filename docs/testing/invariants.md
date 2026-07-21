# Invariants (bound to tests as they are implemented)

Contract-level invariants proven in Commit 2:

- I-C2-1  JSON Schema uses only standard draft 2020-12 keywords.
- I-C2-2  Pace vocabulary is locked; banned names appear nowhere.
- I-C2-3  Generated schemas equal the committed schemas (`make schema-check`).
- I-C2-4  Valid golden workouts pass schema; schema-invalid examples are rejected.
- I-C2-5  No general `IncidentStarted` / `IncidentResolved` event names; StopPause terms used.
- I-C2-6  `activeDurationSec` / `stoppedDurationSec` / `elapsedDurationSec` present on
          length/report contracts.
- I-C2-7  `performanceRelatedStopProbability` is optional/advisory on the efficiency contract.
- I-C2-8  External records require `data_domain` to merge; no production-eligibility flag;
          synthetic records carry `synthetic=true` + provenance.

Behavioural invariants (StopPause, safety controller, replay, simulator) are added with
their commits (3–10).

## Mainline invariants (approved pace profiles)

- I-M-1  Approved-profile leg durations sum exactly to `targetTotalTimeSec` (tol 1e-6); the
         core never silently normalizes.
- I-M-2  A profile's compiled timeline duration equals its `targetTotalTimeSec`.
- I-M-3  Profile selection is deterministic and returns the highest-authority eligible
         candidate; an equal-priority tie raises rather than picking silently.
- I-M-4  A DRAFT/REJECTED profile can never start a session.
- I-M-5  A coach-locked profile never receives ML/rule auto-apply (`COACH_PROFILE_LOCKED`).
- I-M-6  Official completed distance is always a pool-length multiple and never exceeds the
         workout total; wearable estimates never rewrite it.
- I-M-7  Profile legs are not official wall splits.
- I-M-8  Resolved start mode is never ambiguous (repeat → block → default).
- I-M-9  ML request with missing confidence or data quality abstains
         (`ML_CONFIDENCE_MISSING` / `DATA_QUALITY_MISSING`), never APPLY.

## Commit 7 invariants (append-only journal + replay, ADR-037)

- I-C7-1   One command's events are exactly one `EventBatchRecord` and one canonical JSONL
           line; a torn final line removes the whole command batch (no half command).
- I-C7-2   The canonical codec is byte-deterministic (UTF-8, no BOM, `sort_keys`, compact,
           one `\n`); NaN/Infinity are rejected on encode and decode.
- I-C7-3   `append_batch` reports success only after write **and** fsync complete; on file
           creation the parent directory is synced too.
- I-C7-4   Resending the exact same batch never writes a second line
           (`ALREADY_PRESENT`); a same-seq/command-id/overlap difference is a conflict.
- I-C7-5   After an fsync failure the fully-written line is recognised on retry; the line
           is never auto-deleted, and a later batch can still append.
- I-C7-6   A torn final line is truncated only in repair mode (`LogTailTruncated`, exact
           byte counts); bytes before the last complete newline are never touched.
- I-C7-7   A valid-but-unterminated final record is retained; repair appends only `\n`
           (`MissingFinalNewlineRepaired`), which is not data loss.
- I-C7-8   Middle corruption, a newline-terminated invalid final line, and blank lines are
           `CorruptEventLogError`; corruption is never skipped.
- I-C7-9   Replay executes no commands, never rewinds runtime clocks, and uses no
           time/randomness/uuid/filesystem; identical events → identical state.
- I-C7-10  `elapsed = active + stopped` and `wall = elapsed + lifecyclePaused` always hold
           and are all non-negative; a violation raises `ReplayDurationError`.
- I-C7-11  The retroactive StopPause start is the payload `startedAtMs`, never the
           confirmation event timestamp; StopPause never changes the lifecycle state.
- I-C7-12  Replayed official distance is a pool-length multiple from geometry; a wearable
           source never rewrites it.
- I-C7-13  Golden journals are byte-deterministic — committed bytes equal the regenerated
           bytes and are sha256-equal across directories.
- I-C7-14  `SessionRecovered` is never auto-produced or auto-appended; on replay it changes
           no lifecycle state and only increments `recoveryCount`.

## Commit 8 invariants (continuous pace curves + simulator, ADR-038)

- I-C8-1   A leg/split/total duration is a time constraint; within-length pace comes from the
           approved curve.
- I-C8-2   Approved curve knot speeds are strictly positive and finite; zero/negative is
           rejected.
- I-C8-3   Compilation is deterministic and bit-identical for the same profile.
- I-C8-4   The integrated total equals the target within `CURVE_TIME_TOLERANCE_SEC`; each
           locked split equals its target within the same tolerance.
- I-C8-5   Reconciliation rejects (never clamps) on negative remainder, non-finite/non-positive
           speed, or a post-reconciliation physical-bound violation.
- I-C8-6   The `CurveValidationSummary` is recomputed by the compiler; only `validationPassed`
           runs live.
- I-C8-7   Two different curves with the same total and same locked splits yield equal wall
           times but may differ mid-length (Demonstration A).
- I-C8-8   1.0→1.1 migration preserves the timeline (leg boundaries bit-identical), never
           smooths, and never mutates the input (Demonstration B).
- I-C8-9   Both profile versions are selectable/compilable; the GhostClock is unchanged.
- I-C8-10  A coach continuous-curve reset applies only at a safe official wall, adds no stopped
           duration, freezes no clock, and preserves prior splits (not a StopPause).
- I-C8-11  Official distance stays wall/geometry authoritative; a wearable estimate never
           rewrites it.
- I-C8-12  The PCHIP implementation is defined exactly once, in `swimcore.pacing`.
- I-C8-13  The simulator redefines no core type and duplicates no curve/pace/ghost/clock/
           safety/replay logic; it embeds the real runtime.
- I-C8-14  A scenario produces byte-identical journals across runs; provenance marks
           `usedRealHumanData=False` and `SYNTHETIC_SIMULATION`.
- I-C8-15  Live runtime never runs planning ML or a PCHIP solve; it consumes a precompiled
           timeline.
