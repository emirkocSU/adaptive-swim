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

**Commit 4 pace math is not written yet.** Rule-009 uses a small, isolated rest estimate
(even/controlled/negative: `distance * targetPace / 100`; progressive: the mean of start
and end pace) that will be swapped for the real pace engine in Commit 4.

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
