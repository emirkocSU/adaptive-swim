# CLAUDE.md — Coding Agent Contract (Adaptive Swim Pacing Platform)

This file is the operating contract for any coding agent (or human) working in this
repository. It is authoritative. Read it before writing code.

## Non-negotiables (from the approved architecture v1.1 + StopPause addendum)

1. No LLM / Gemini / Claude API in the critical product path. Guided chat is a
   deterministic state machine; reports are template + reason code.
2. The live pacing loop is fully offline. No cloud call during a live session.
3. ML never controls the light or the ghost directly. Every ML output passes through
   the deterministic `SafetyController`. Low confidence / low data quality → abstain →
   coach plan.
4. Heart rate is never a stop-or-adapt reason on its own.
5. Continuous underwater Bluetooth is never assumed.
6. MVP is single-lane, single-ghost, modular monolith (not microservices).
7. `swimcore` is pure: no I/O, no framework, no DB, no hardware, no network. Time only
   enters through an injected `Clock`/`TimestampProvider` protocol.
8. The simulator runs the real `swimcore` embedded. Writing a second pacing/ghost
   implementation inside the simulator is forbidden.
9. Manual splits are not ground truth. Split quality is a five-class flag.
10. Core IP stays with the founder. `swimcore` must remain separable.

## Ghost alignment rule (StopPause model — CORRECTED)

Repositioning the ghost mid-length while unverified, or during normal / large pace loss,
is **forbidden**. However, during a **verified StopPause**, controlled mid-pool ghost
alignment to the swimmer's currently tracked position **is allowed**. Official workout
accounting — length / split / set / repetition / rest flow — is **reconciled at the next
valid wall**.

Three distinct behaviours must never be conflated:

- **Normal / large pace loss** → ghost stays `ACTIVE` and keeps moving; the gap is
  preserved; the workout clock keeps running; the data counts toward performance.
- **Coach pacing reset** → a separate command. Previous poor performance stays in the
  report (it is not erased); a new pacing reference starts only at the next valid wall;
  the workout clock does **not** stop. This is **not** a StopPause.
- **StopPause (long stop / manual incident)** → once the threshold is exceeded (default
  10s, coach-configurable) the logical workout clock freezes retroactively from the
  moment the stop began; the ghost aligns to the swimmer's tracked position (mid-pool is
  allowed) and waits with them; length/set/rest are finalized at the next wall. Stopped
  time is removed from active pace but shown explicitly in the report.

## Terminology

- The general runtime behaviour is named **StopPause** (not "incident pause").
- **Incident** survives only as a *trigger/reason*: `StopPauseTrigger.MANUAL_INCIDENT`.
- Do not use "coach-marked incident" or "incident during rest" as behaviour names.
- Event names use StopPause terminology (`StopDetected`, `LongStopConfirmed`,
  `StopPauseStarted`, `StopPauseResolved`). `IncidentStarted` / `IncidentResolved` are
  banned as general event names.

## Dependency rules (enforced by import-linter, `.importlinter`)

Layer order (upper may import lower; never the reverse):
`swimtools > simulator > persistence > swimcore > contracts`.

- `swimcore` MUST NOT import `contracts.external_data` (external-data plan contracts may
  never reach the runtime).
- `contracts` MUST NOT import any inner package.
- `swimcore` and `contracts` MUST NOT import IO frameworks (FastAPI, SQLAlchemy,
  sqlite3, socket, requests, httpx).

## Pace field vocabulary (locked)

Use exactly: `targetPaceSecPer100M`, `suggestedPaceSecPer100M`, `appliedPaceSecPer100M`,
`fastestAllowedPaceSecPer100M`, `slowestAllowedPaceSecPer100M`. In sec/100m, smaller = faster,
so `fastestAllowedPaceSecPer100M <= targetPaceSecPer100M <= slowestAllowedPaceSecPer100M`.
`minPace`, `maxPace`, `coachMinPace`, `coachMaxPace` are banned everywhere.

## Two-layer workout validation

- Layer 1 — JSON Schema (structural): only standard draft 2020-12 keywords. No custom
  keywords (`multipleOfPoolLength`, `contiguousCoverage`, ...). Handles shape, types,
  ranges, and `additionalProperties: false` only.
- Layer 2 — pure Python semantic validator (**Commit 3, done**), in `swimcore/workout/`:
  `validate_workout(workout, context=None) -> WorkoutValidationResult`. Ten rules
  (RULE-001…010): contiguous coverage, pool-length multiple, pace-bounds direction,
  progressive mode, adaptation-bounds consistency, feedback capability, total distance,
  ghost-source references, rest-interval sanity, schema version. Pure and deterministic:
  no I/O/DB/network, never mutates input, returns all issues in one pass, ordered by
  (block, segment, rule). `ValidationIssue = path + rule + message + severity`; severity is
  `ERROR`/`WARNING` and only `ERROR` sets `isValid = False`.
- External facts arrive via an injected `WorkoutValidationContext`; without it,
  context-dependent rules degrade to a documented WARNING. `migrations.py` = pure
  `1.0 → 1.0` no-op only.
- **Commit 4 pace math is not written yet.** Rule-009 uses an isolated rest estimate to be
  replaced by the real pace engine in Commit 4.

## Pace math engine (Commit 4, done — `swimcore/pacing/`)

Pure, deterministic, clock-independent active-swimming pace math. Files: `types.py`
(`EPSILON=1e-9`, frozen `PacePoint/PaceInterval/PaceTimeline/DistanceAtTimeResult/`
`TimeAtDistanceResult`), `math.py` (`duration_for_distance`/`distance_for_duration` +
NaN/inf guards), `curves.py` (linear pace curve, exact integral + quadratic inverse,
`ControlledStartProfile`, `resolve_curve_endpoints`), `timeline.py`
(`compile_pace_timeline`, `target_active_time_at_distance`,
`ghost_distance_at_active_time(clamp=...)`, wall helpers), `errors.py` (domain exceptions).

Rules: no I/O, no clock, no randomness, no global state, immutable inputs (never mutate
contract models), imports only `contracts` + stdlib. Timeline carries **active swim time
only** — rest/StopPause/real-elapsed excluded. No second pace formula may exist in the
simulator. StopPause freeze, pacing-reset runtime, ML pace, and SafetyController are NOT
in this commit.

## Commands / test expectations

`make ci` must stay green. Every change tests the invariant it touches. Generated JSON
Schema files are produced by `python -m swimtools.gen_schemas` and verified by
`make schema-check`; never hand-edit `src/contracts/schemas/*.json`.

## Forbidden shortcuts

- Adding I/O to `swimcore`.
- Hand-editing generated schema files.
- A second pacing/ghost implementation in the simulator.
- Modelling StopPause exclusion as `Split.qualityFlag = INVALID` (they are separate axes).
- Repositioning the ghost mid-length while unverified or during normal/large pace loss.
- Opening a `cloud/`, `ml/`, `ui/`, or partner-adapter package in Phase 1.

## Phase 1 boundary

No cloud, no real ML runtime, no UI/PWA, no device driver, no database, no FastAPI, no
wearable connector. Phase 1 is a headless, offline, deterministic core.
