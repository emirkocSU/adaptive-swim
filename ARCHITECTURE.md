# ARCHITECTURE.md — Living Summary

Baseline: **Local-First, Simulator-First Modular Monolith + Python Edge Runtime**
(architecture v1.1). Phase 1 is the headless core; cloud, ML, UI, and hardware are
deferred to later phases behind explicit triggers.

## Package layering (enforced by `.importlinter`)

```
swimtools > simulator > persistence > swimcore > contracts
```

`swimcore` and `contracts` are pure (no I/O, no framework, no DB, no network). `swimcore`
may not import `contracts.external_data`.

## Core loop (conceptual)

Coach workout → two-layer validation (JSON Schema + semantic validator) → session state
machine → ghost clock (pure `pace_function(t)`) → SafetyController (deterministic) →
PaceTarget → device adapter (later phase). ML, when it exists, only feeds the
SafetyController and can only abstain back to the coach plan.

## Two-layer workout validation

Validation is split into two independent layers:

1. **JSON Schema (structural only).** The generated `workout-1.0.json` schema checks
   shape, types, required fields, ranges, and `additionalProperties: false`. It carries no
   custom keywords and encodes no semantic/domain rule.
2. **Semantic validator (Commit 3, `swimcore/workout/`).** A pure, deterministic domain
   layer: `validate_workout(workout, context=None) -> WorkoutValidationResult`. It runs ten
   rules (contiguous coverage, pool-length multiples, pace-bounds direction, progressive
   mode, adaptation-bounds consistency, feedback capability, total distance, ghost-source
   references, rest-interval sanity, schema version), collects **all** issues in one pass,
   never mutates its input, and performs **no I/O, DB, network, or filesystem** access.

Each `ValidationIssue` has `path` (machine-readable, e.g.
`blocks[0].segments[2].fromM`), `rule`, `message`, and `severity`. Severity is `ERROR` or
`WARNING`; **only an ERROR makes a workout invalid** (`isValid == not errors`). Issue order
is deterministic: (block index, segment index, rule code).

External facts a rule needs (supported schema versions, `maxTotalWorkoutDistanceM`, known
completed-session ids, coach-benchmark profile refs, supported feedback capabilities,
strict-boundary mode) arrive through an injected `WorkoutValidationContext` — never by
importing a DB or device. When no context is supplied, context-dependent rules degrade to a
documented WARNING (e.g. a ghost reference becomes `REFERENCE_NOT_VERIFIED`) rather than
failing silently. `migrations.py` holds a pure `1.0 → 1.0` no-op registry; no speculative
future migrations exist.

Rule-009 (rest sanity) shares the **single** Commit-4 pace formula
(`swimcore.pacing.curves.segment_active_duration_sec`) — there is no second pace estimate in
the validator. The semantic validator currently runs **twelve** rules (RULE-001 … RULE-012,
the last two covering controlled-start and negative-split ordering).

## Pace math engine (Commit 4, `swimcore/pacing/`)

A pure, deterministic, clock-independent module that turns a workout into a target pace
timeline over **active swimming time only** (rest excluded; StopPause and real elapsed time
are later-commit runtime concerns). Every segment mode reduces to a linear pace curve
`p(x) = p0 + (p1 - p0)·x/L` (sec/100m, smaller = faster): even/negative-split → constant,
controlled_start → start→target, progressive → target→end. Active time is the exact
integral `T(x) = (p0·x + (p1−p0)·x²/2L)/100`; the inverse `x(T)` uses the true quadratic
root, never a linear time/distance-ratio guess.

Public API: `compile_pace_timeline(workout)`, `target_active_time_at_distance(timeline, d)`,
`ghost_distance_at_active_time(timeline, t, clamp=False)`, the constant-pace helpers
`duration_for_distance` / `distance_for_duration`, and wall helpers `is_wall_boundary` /
`previous_wall_boundary` / `next_wall_boundary`. `EPSILON = 1e-9` is the single tolerance.
NaN/infinity are rejected; explicit domain errors live in `pacing/errors.py`. The engine
imports only `contracts` + the standard library (enforced by import-linter and the
`arch_check` AST purity scan). In `20.00 +15.00`, the `20.00` active part comes from here;
the `+15.00` stopped part is future StopPause runtime accounting.

## Deterministic clocks & ghost primitive (Commit 5, `swimcore/time/`, `swimcore/ghost/`)

`SimClock` is a manually-advanced, bit-identical clock (no system time / sleep / randomness /
I/O) satisfying the existing `contracts.events.Clock` protocol. `ActiveClock` separates real
(wall) time from active swimming time: `active = wall - confirmed stopped intervals`. A
StopPause freezes **retroactively** — a stop that began at 10 s but was confirmed at 20 s
pins active time to its 10 s value for the whole frozen window, and on resume the
`[stop_start, resumed]` interval is removed permanently. `ActiveClock` is a **monotonic runtime** timing
primitive — not an event store and not a session state machine: it advances a
forward-only watermark on **every** observation (transitions *and* queries) and rejects any
snapshot or query earlier than that watermark (`InvalidClockTimeError`) — so a later snapshot
can never rewind the active time, and a StopPause confirmation cannot land in the past, and a resume may not precede
the StopPause confirmation time. It never *detects* a stop. Historical replay is reconstructed
from events in Commit 7, not from this clock.

`GhostClock` advances the Commit-4 pace timeline by active time. It never tracks the real
swimmer or measures pace loss — on a normal/large pace loss the ghost stays ACTIVE and keeps
moving; no automatic alignment happens. During an externally confirmed StopPause the ghost
aligns to an externally supplied `tracked_alignment_distance_m` (never estimated, not required
to be reported) and holds. An explicit immutable `GhostAnchor`
(`anchorActiveElapsedSec`, `anchorTimelineDistanceM`, `anchorDisplayDistanceM`) keeps
`displayDistanceM = anchorDisplay + (timelineDistance(activeNow) - anchorTimeline)`, so the
ghost resumes from where the swimmer stopped instead of snapping back to the plan. Two
positions stay strictly separate: `timelineDistanceM` (unchanging mathematical plan position)
and `displayDistanceM` (after the temporary alignment offset). Mid-pool alignment is
temporary; `reconcile_at_wall` converts it into a safe forward wall anchor at the next valid
wall — it does not change length/set/split state or start rest (that is Commit 6). In
`20.00 +15.00`, `20.00` is the ActiveClock active time and `+15.00` is stopped elapsed.

## Ghost / StopPause model (supersedes the earlier "re-anchor-only-at-wall" idea)

Three separate behaviours:

| Situation | Ghost | Workout clock | Counts toward performance |
|---|---|---|---|
| Normal / large pace loss | keeps moving (`ACTIVE`) | keeps running | yes |
| Coach pacing reset | new reference at the next wall | keeps running | previous loss stays in report |
| StopPause (long stop / manual incident) | aligns to the swimmer (mid-pool allowed) and waits | frozen from the moment the stop began | stopped time removed from active pace, shown explicitly |

Key rules: the general behaviour is **StopPause**; `MANUAL_INCIDENT` is only a *trigger*.
During a verified StopPause, controlled mid-pool ghost alignment is allowed, but official
length/set/rest accounting is reconciled at the next valid wall. StopPause exclusion is a
separate axis from split measurement quality — a `VERIFIED_HIGH` split is never turned
`INVALID` because of a StopPause.

## Duration accounting

Each length/report carries three durations: `activeDurationSec`, `stoppedDurationSec`,
`elapsedDurationSec`, displayed as `active +stopped` (e.g. `20.00 +15.00` = 35.00 total).
If stop timing/alignment is reliable, the length is not discarded (active and stopped are
kept separate); if unreliable, the length may be excluded from analysis.

## What is NOT here in Phase 1

`cloud/`, `ml/` runtime, `ui/`, device drivers, partner adapters, database, FastAPI,
wearable connectors, rule-based/ML adaptation engines. These arrive in later phases with
their own ADRs and triggers.
