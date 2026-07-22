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
11. ML plans; the deterministic core executes approved plans. Plan generation and live
    adaptation are separate concerns and are never conflated (ADR-035).
12. A coach-authored / coach-locked profile has the highest authority. ML and rule-based
    sources cannot auto-override it (`COACH_PROFILE_LOCKED`); they may only suggest.
13. Start mode and pool length are mandatory workout execution context (Workout 1.1,
    ADR-036). The resolved start mode is never ambiguous.
14. Wearable estimated distance never rewrites official distance and never jumps the ghost;
    official distance comes only from workout geometry / verified walls (ADR-036).
15. Profile legs are not official wall splits. Leg boundaries are analytical; official
    splits come only from verified wall boundaries (ADR-034/036).
16. Natural planned sprint fade (a short-distance positive split) is not a StopPause and not
    an incident; the `SafetyController` must not treat it as a pace collapse.

17. One command's events are exactly one `EventBatchRecord` = one canonical JSONL line; a
    torn final line removes the whole command batch (a partial command never replays).
18. A journal append reports success only after write **and** fsync; the final partial line
    is recoverable and middle corruption is never skipped or auto-repaired.
19. Historical replay is pure and event-derived: it runs no commands, never rewinds the
    runtime clocks, and reuses the authoritative transition table (no second state machine).
20. Lifecycle pause and StopPause are separate duration axes; `elapsed = active + stopped`
    and `wall = elapsed + lifecyclePaused` always hold. The retroactive StopPause start is
    the payload `startedAtMs`, never the confirmation timestamp.
21. Commit 7 adds no SQLite/DB/ORM/WAL, no simulator/analytics/UI, and no network; SQLite is
    a Faz 2 projection (ADR-003). `swimcore` never imports `persistence`.
22. `SessionRecovered` is never auto-produced or auto-appended when reading a journal; on
    replay it changes no lifecycle state and only increments `recoveryCount`.
23. A profile leg duration is a time constraint, not proof of constant within-leg speed
    (ADR-038).
24. Approved continuous curves are compiled before the live session.
25. Live runtime never calls planning ML.
26. The PCHIP implementation exists only in `swimcore.pacing`.
27. The simulator must never duplicate curve, pace, ghost, clock, safety or replay logic.
28. Official distance remains wall/geometry authoritative.
29. Zero/negative approved target velocity is forbidden.
30. Locked split durations are hard constraints.
31. Exact target-time reconciliation is mandatory (reject, never clamp).
32. Coach continuous-profile replacement applies only at a safe official wall.
33. Coach curve reset is not a StopPause.
34. Synthetic simulator data is never production performance evidence.
35. ADR-037 remains event persistence; continuous curves use ADR-038.

36. **Measured instantaneous velocity ≠ operational target velocity envelope** (ADR-039).
    A generated curve is a *target velocity envelope* / *operational ghost velocity curve*;
    it is never named or described as a predicted measured velocity.
37. A coarse-split-derived, deterministic-baseline, bounded-template or coarse-latent curve
    can never carry `continuousCurveGroundTruth = true` (contract-enforced).
38. Phase labels are never synthesised for data that does not carry them. The continuous
    phase contract serves coach-authored profiles, templates and genuinely labelled data.
39. The first data-driven model is a **sequence-level coarse conditional split prior**, not
    a phase-aware micro model. ADR-038's transformer is a long-term target, not the active
    architecture.
40. Coach target and model forecast are separate fields in separate models. A forecast never
    mutates a coach target; under OOD / domain extrapolation `BOUNDED_AUTO` is forbidden.
41. `swimcore` never reads a dataset, a catalog manifest, a CSV or a ZIP, and never imports
    `contracts.data_assets` or `contracts.forecasting` (import-linter enforced).
42. Raw dataset CSV/ZIP files are never committed, never placed under `src/`, never shipped
    as package data and never used as ordinary CI fixtures. Only `data/catalog/` manifests
    and `data/schemas/` expectations are checked in.
43. A license that is not `VERIFIED_ALLOWED` can never yield production eligibility;
    `productionTrainingEligible = false` cannot be overridden; a quarantined asset serves
    only pipeline smoke tests and never a primary research analysis.
44. Missing dataset metadata is recorded as missing, never fabricated (an unrecorded hash is
    a warning with the measured value, not an invented expectation).
45. No runtime `pandas` / `numpy` / `scipy` dependency; `src/ml/` does not exist before
    Phase 5.
46. Physical-bound validation is **analytic**: PCHIP critical points (speed extrema,
    gradient extrema, acceleration branch-and-bound) are authoritative; sampling is only
    additional evidence. All bounds are re-verified after reconciliation at the reconciled
    scale, and `physicalBoundsChecked = true` is written only when that post-check passed.
47. `+inf`, `-inf` and `NaN` are rejected at the contract boundary; positive infinity does
    not satisfy a "positive number" constraint.
48. The simulator's eight required acceptance scenarios exist under their exact slugs and
    are never aliases of demo scenarios; `--seed` drives the real virtual-swimmer RNG
    (instance-local, never `random.seed()`); the harness itself validates live state
    against a re-read journal replay.

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
- `swimcore` MUST NOT import `contracts.data_assets` or `contracts.forecasting` (dataset
  and forecast plans never reach the runtime).
- `contracts`, `swimcore`, `persistence` and `simulator` MUST NOT import `pandas`, `numpy`
  or `scipy`.
- `simulator` MUST NOT import the dataset catalog/validator/splitting tools — it reads no
  dataset and performs no model inference.

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
  `validate_workout(workout, context=None) -> WorkoutValidationResult`. Twelve rules
  (RULE-001 … RULE-012): contiguous coverage, pool-length multiple, pace-bounds direction,
  progressive mode, adaptation-bounds consistency, feedback capability, total distance,
  ghost-source references, rest-interval sanity, schema version. Pure and deterministic:
  no I/O/DB/network, never mutates input, returns all issues in one pass, ordered by
  (block, segment, rule). `ValidationIssue = path + rule + message + severity`; severity is
  `ERROR`/`WARNING` and only `ERROR` sets `isValid = False`.
- External facts arrive via an injected `WorkoutValidationContext`; without it,
  context-dependent rules degrade to a documented WARNING. `migrations.py` = pure
  `1.0 → 1.0` no-op only.
- Rule-009 (rest sanity) calls the shared Commit-4 pace math
  (`swimcore.pacing.curves.segment_active_duration_sec`); the validator and the pace engine
  use exactly one pace formula. Commit 4 (pace engine) is **done**.

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

## Deterministic clocks & ghost (Commit 5, done — `swimcore/time/`, `swimcore/ghost/`)

`SimClock` (manual, monotonic, bit-identical; satisfies `contracts.events.Clock`).
`ActiveClock` splits wall vs active time; `active = wall - confirmed stopped`; StopPause
freezes retroactively from the real stop start and stays fixed until resume. It is a
**monotonic runtime clock** (not an event store): every observation (query or transition) advances a
forward-only watermark, so a later snapshot can never rewind active time and a StopPause
confirmation cannot precede the last observed time; resume may not precede confirmation. `reconcile_at_wall` runs once, only at the next
valid wall after the tracked alignment (authoritative Commit-4 wall helper). `GhostClock`
drives the Commit-4 timeline by active time, aligns to an **externally supplied** tracked
point only during a confirmed StopPause, uses an immutable `GhostAnchor` so it never jumps
back to the plan, and `reconcile_at_wall` turns temporary mid-pool alignment into a forward
wall anchor. States: ACTIVE / STOP_PAUSED only.

Rules: pure, clock-injected, no I/O/sleep/randomness/`time.time()`/`datetime.now()`. Keep
`timelineDistanceM` (plan) and `displayDistanceM` (aligned) separate. No stop *detection*, no
swimmer-position estimation, no events/persistence, no session commands, no SafetyController,
no second GhostClock in the simulator. Those are Commit 6+.

## Session orchestration & SafetyController (Commit 6, done — `swimcore/session/`, `swimcore/control/`)

`SessionAggregate.handle(command) -> list[EventEnvelope]`: pure deterministic state machine
(CREATED/ARMED/RUNNING/PAUSED/COMPLETED/ABORTED) + idempotency (`clientCommandId`) + typed
in-memory events. StopPause is NOT a lifecycle state — session stays RUNNING, ghost
STOP_PAUSED, active clock frozen. `RecordSplit` at the expected wall reconciles the pending
alignment once. Coach pacing reset applies only at the next valid wall; never stops clock /
repositions ghost mid-pool / erases performance. All pace changes go through the pure
`SafetyController` (fastest/slowest/max-change bounds; off/suggest_only/low-conf/low-quality/
not-at-wall abstain; NaN/inf/heart-rate-only reject; reason codes always present). Time +
event ids injected; inputs never mutated; atomic (validate before mutating clock/ghost).

Do NOT add here (in the Commit-6 session layer): persistence, replay, filesystem, DB, network, cloud, UI/FastAPI, real
simulator swimmer, wearable/sensor processing, ML runtime, analytics report, hardware adapter
(Commit 7+). Do not rewrite pace/ghost/clock implementations.

## Persistence & replay (Commit 7, done — `persistence/`, `swimcore/replay/`, ADR-037)

`contracts.event_log.EventBatchRecord`: one command's events as one canonical JSONL line
(schema `event-batch-record-1.0.json`). `persistence.JsonlSessionEventLog`: append-only,
fsync-per-command-batch, parent-dir sync on create, partial-write/EINTR-safe, exact-duplicate
idempotency (`ALREADY_PRESENT`), `EventLogDurabilityUncertainError` retry, explicit tail
recovery (`recover_and_read` → `LogTailTruncated` for a torn tail, `MissingFinalNewlineRepaired`
for a valid-but-unterminated final record); middle corruption / newline-terminated invalid
final line / blank line → `CorruptEventLogError`. `persistence.build_session_recovered_event`
is the only producer of `SessionRecovered` (injected Clock/EventIdGenerator; never
auto-appended). `swimcore.replay.replay_session` folds events into `HistoricalSessionState`
(pure; reuses the transition table; separate active/stopped/lifecycle-paused/elapsed/wall axes
with enforced invariants; retroactive StopPause start from payload; geometry-only official
distance). `swimcore` never imports `persistence`; `persistence` may import `swimcore.replay`.

Do NOT add here: SQLite/DB/ORM/WAL (Faz 2, ADR-003), network/web, a simulator, analytics, or
a live command-ready aggregate recovery; do not rewrite the session transition table.

## Continuous pace curves & simulator (Commit 8, done — ADR-038)

`ApprovedPaceProfile` **1.1** (`contracts/continuous_pace.py`): a leg/split duration is a
*time constraint*; within-length pace is an approved **curve** (PCHIP native;
CONSTANT_SPEED for legacy/templates). Curve knots carry strictly-positive finite speed.
`swimcore/pacing/pchip.py` is the single Fritsch–Carlson PCHIP (no SciPy/NumPy).
`continuous_profile_compiler.py` compiles to the existing `PaceTimeline` with **exact
total-time + locked-split reconciliation** (reject, never clamp; central constants
`CONTINUOUS_CURVE_MAX_STEP_M=0.10`, `CURVE_TIME_TOLERANCE_SEC=1e-6`); it recomputes the
authoritative `CurveValidationSummary` and only `validationPassed` may run live.
`continuous_migration.py` is a pure 1.0→1.1 migration (constant-speed, no smoothing).
Runtime: `select_live_pace_profile`, the aggregate registry and `compile_live_profile`
accept both versions; the GhostClock is unchanged. `CoachPacingReset.replacementPaceProfileRef`
+ `GhostClock.apply_timeline_reset_at_wall` do a **safe-wall** curve swap (not a StopPause:
no clock freeze, no stopped duration, splits preserved). Planning ML (Phase-aware Conditional
Transformer + Spline Decoder) is contract direction only — nothing is trained or run.

Simulator (`src/simulator/`): a deterministic headless harness that drives the **real**
`SessionAggregate` + real `JsonlSessionEventLog` + real replay — it duplicates no core logic.
The virtual swimmer is a **tick-based** deterministic simulation (default 100 ms ticks)
producing an immutable observation per tick (wall/active time, actual + target distance and
speed, gap, phase, position quality, planned-rest flag); official wall crossings are found
by deterministic interpolation inside the crossing tick. It queries the real timeline for
targets and never re-implements PCHIP or the compiler. Randomness comes from an
instance-local splitmix64 PRNG seeded explicitly — `--seed` reaches that RNG, and
`random.seed()` is forbidden.

The eight required acceptance scenarios (exact slugs, no aliases): `normal-pace-loss`,
`long-stop-mid-length`, `manual-stop-at-verified-wall`, `duplicate-stop-mark`,
`stop-during-planned-rest`, `unreliable-position-time`, `complete-while-stop-paused`,
`coach-continuous-curve-reset`. Older demo scenarios remain as helper examples only.

Each run carries a `SimulationRunManifest` (`synthetic=true`, scenario id/version and
digest, seed, simulator/harness versions, workout ref/digest, all selected/replacement
profile digests and identities, analytics-policy digest, curve representation and compiler
version). `runId` hashes that complete deterministic input set — no timestamp, UUID or path.
The harness re-reads its own journal, replays it and fails the run on any live/replay
mismatch. Do NOT: run planning ML live, add
a second PCHIP or ghost/clock, clamp reconciliation, treat a coach curve reset as a
StopPause, let a wearable estimate become official distance, alias a required scenario to a
demo, or treat synthetic data as performance evidence.

## Dataset catalog & model planning (Commit 8 correction — ADR-039)

`data/catalog/*.json` holds typed `DatasetAssetManifest` records (hashes, row/column counts,
required columns, roles, license, eligibility, restrictions, grouping keys, leakage rules);
`data/schemas/*.json` holds the per-dataset expectations. Raw bundles live in the gitignored
`data/external/raw/` and are validated on demand by
`python -m swimtools.validate_dataset_bundle` — stdlib-only streaming (`zipfile`, `csv`,
`hashlib`), bounded memory, rejecting zip-slip, duplicate and unexpected members.
`swimtools.data_catalog` enforces the license/quarantine gates with typed errors and
`swimtools.data_splitting` provides pure leakage validators. `contracts/forecasting.py`
keeps coach target and model forecast strictly separate. Commit 8 adds contracts, catalog,
validators, leakage guards, feature utilities and planning docs **only** — no `src/ml/`, no
training run.

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
- Committing a raw dataset CSV/ZIP, or loading one as an ordinary CI fixture.
- Aliasing a required simulator scenario to a demo scenario.
- Treating a grid sample as proof that a curve respects its physical bounds.
- Calling a generated curve a predicted measured velocity.

## Phase 1 boundary

No cloud, no real ML runtime, no UI/PWA, no device driver, no database, no FastAPI, no
wearable connector. Phase 1 is a headless, offline, deterministic core.

## Distance-specific approved pace profiles (mainline, pre-Commit 7 — done)

`ApprovedPaceProfile` (`src/contracts/pace_profiles.py`) is the single authoritative live
plan input. Legs cover the distance with no gap/overlap; leg durations sum exactly to
`targetTotalTimeSec` (no silent normalization). Selection authority:
`COACH_AUTHORED > COACH_APPROVED_MODEL > DEFAULT_MODEL_GENERATED` (default-model needs an
explicit opt-in; ties raise). `compile_approved_pace_profile` runs the approved profile
deterministically (constant leg pace, bit-identical timeline; rest/StopPause/lifecycle-pause
excluded). Workout 1.1 (`WorkoutTemplateV1_1`) adds `StartPolicy`, per-block/per-repeat start
overrides, and `workoutGoal`; migration 1.0→1.1 is explicit (`migrate_workout_1_0_to_1_1`,
start mode never guessed). SafetyController gains `profileSource` / `profileCoachLocked` /
`currentProfileLegIndex` / `currentTargetPaceSecPer100M`; ML missing confidence/quality →
distinct `ML_CONFIDENCE_MISSING` / `DATA_QUALITY_MISSING` abstain; coach-locked →
`COACH_PROFILE_LOCKED`. See ADR-034/035/036.

## Planning ML vs live adaptation ML

Two separate models and gates. The pre-session planning model produces DRAFT profiles and
must pass the Planning Model Gate **P1–P7** before it can be a live plan source; without it,
templates/manual/legacy segments keep the product complete. The live adaptation model keeps
the existing G1–G7 gate and always runs behind the SafetyController. Neither ever controls
the ghost/clock/StopPause directly.

## Commit 9 analytics non-negotiables (ADR-040)

- Session reports are derived artifacts, not domain events.
- Historical replay is the authoritative starting point for reports.
- Analytics never mutates session state and never emits commands/events.
- Missing data is never replaced with fabricated zero values.
- Official distance uses only official wall/geometry authority already carried by replay.
- Target and forecast fields remain separate; target is never overwritten by prediction.
- Continuous curve metrics require trusted, finite, monotonic observations.
- Raw instantaneous stroke-cycle velocity is not the operational target envelope.
- StopPause, lifecycle pause, planned rest and coach reset are separate concepts.
- Coach reset never rewrites historical split/profile provenance.
- HR and stroke analytics remain advisory and optional.
- Dataset evidence is copied only from approved profile provenance; analytics reads no raw data.
- Synthetic simulator reports are not real performance evidence.
- Report identifiers are content-addressed and include effective workout/profile/timeline,
  replacement registry, observation, sensor and analytics-policy inputs through provenance digests.
- Report schema version is contract-owned and fixed to SessionReport 1.1 for the Commit 9 builder.
- Coach-reset reports require the referenced replacement profile/timeline registry; no fallback to
  the initial profile is allowed.
- Workout, profile, timeline and replay-selected identities/geometry must agree before reporting.
- Trusted observations must be inside the session horizon; position-time and smoothed-velocity
  observations are supported, but neither creates official distance.
- Pending StopPause wall reconciliation is never reported as completed.
- Planned rest never dilutes non-rest observation quality ratios.
- Report persistence rejects non-canonical JSON bytes.
- Directional split extrema are `None` when that error direction does not exist.
- Report identifiers, canonical JSON bytes and hashes are deterministic.
- `analytics` is pure: no filesystem, network, random, wall clock, ML framework, persistence,
  simulator or swimtools import.


## Commit 10 / Phase 1 closure non-negotiables (ADR-041)

- Phase 1 e2e tests use real public components, never mock core implementations.
- Live state, historical replay and reports must agree.
- E2E artifacts are canonical and deterministic.
- Output paths never affect artifact bytes.
- Official distance remains geometry and verified-wall authoritative.
- StopPause, lifecycle pause, planned rest and coach reset remain separate.
- Failed commands never produce persisted events.
- Report generation never mutates session state.
- Dataset evidence is not session performance evidence.
- Raw external datasets are not part of the runtime package.
- Commit 10 closes Phase 1 and does not start ML development.
- `e2e` owns no domain logic: no PCHIP, no replay reducer, no report metric computation.
- `contracts`, `swimcore`, `persistence`, `analytics` and `simulator` never import `e2e`.
- The e2e layer uses no wall clock, no randomness, no UUID and no network.
- Run and manifest identities are content addressed; a single changed byte changes them.
- A verification check that cannot apply is explicitly `NOT_APPLICABLE`, never silently skipped.
- Golden e2e bundles are a release regression contract: byte drift must be explained, not
  re-baselined by reflex.
- Migration equivalence is asserted on the compiled target function (totals and endpoints
  exact, sampled targets within `MIGRATION_TARGET_TOLERANCE_SEC`), not on the interval
  partition, because the legacy leg representation and the continuous-curve grid legitimately
  differ in granularity.
