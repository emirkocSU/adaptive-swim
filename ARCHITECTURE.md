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

## Session orchestration & SafetyController (Commit 6, `swimcore/session/`, `swimcore/control/`)

The session aggregate is a pure, deterministic domain object that combines the contracts,
semantic validator, pace timeline, ActiveClock, GhostClock, and SafetyController into one
in-memory flow. `handle(command) -> list[EventEnvelope]` dispatches typed commands, enforces
the lifecycle state machine (CREATED → ARMED → RUNNING ⇄ PAUSED, → COMPLETED/ABORTED), and
produces typed domain events with a monotonic session-local sequence. Time and event ids are
injected (no system clock/randomness); input models are never mutated; persistence and
replay live one layer up (Commit 7, see below).

**StopPause is not a lifecycle state.** During a confirmed StopPause the session stays
RUNNING, the ghost is STOP_PAUSED, and the active clock is frozen. `MarkStopPause` drives
`GhostClock.apply_stop_pause` (which validates the alignment before freezing the clock, so a
bad alignment never leaves the clock frozen — atomicity). Wall reconciliation is orchestrated
by `RecordSplit`: a wall split matching the expected reconciliation wall reconciles the
pending mid-pool alignment exactly once. Coach pacing reset is requested any time in RUNNING
but applied only at the next valid wall split; it never stops the clock, repositions the ghost
mid-pool, or erases prior performance.

Every pace change flows through the **SafetyController** — a pure decision function (it never
touches session state, events, the ghost, the clock, or persistence). Smaller sec/100m is
faster; applied pace can never be faster than the fastest limit, slower than the slowest
limit, or exceed the max change per length. `adaptationMode == off` or `suggest_only`, low
confidence, low data quality, or not-at-a-wall all abstain to the coach plan; NaN/inf or
heart-rate-only suggestions are rejected. Every decision carries reason codes. Idempotency is
per `clientCommandId` (same content → same stored events, no re-mutation; different content →
conflict). Accounting: `active = ActiveClock`, `stopped = confirmed StopPause`, `elapsed =
active + stopped`.

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

## Persistence & historical replay (Commit 7, `persistence/`, `swimcore/replay/`, ADR-037)

Durability is log-first. All events of one `handle(command)` call are one
`EventBatchRecord` = one canonical JSONL line (`persistence.codec`: UTF-8, no BOM,
`sort_keys`, compact, one `\n`, NaN/Infinity rejected). `JsonlSessionEventLog` appends
append-only and `os.fsync`s per command batch (parent dir synced on file creation),
reporting success only after write **and** fsync; the write loop is partial-write- and
EINTR-safe. Resending the exact same batch is idempotent (`ALREADY_PRESENT`); an fsync
failure is a typed `EventLogDurabilityUncertainError` whose line is recognised on retry.
Recovery is explicit: a torn final line is truncated only via `recover_and_read()`
(`LogTailTruncated`), a valid-but-unterminated final record is repaired with only a newline
(`MissingFinalNewlineRepaired`), and any middle corruption is `CorruptEventLogError` (never
skipped). `fsync` is a durability *request*: surviving `kill -9` is not surviving a power
cut, and no hardware guarantee is claimed.

`swimcore.replay.replay_session` is pure: it folds typed events into a
`HistoricalSessionState` read model. It executes no commands, never rewinds the runtime
`ActiveClock`/`GhostClock`, reconstructs no exact mid-pool ghost metre, and reuses the
authoritative transition table (no second state machine). Duration axes are separate and
invariant-checked (`elapsed = active + stopped`, `wall = elapsed + lifecyclePaused`); the
retroactive StopPause start comes from the payload, not the confirmation timestamp; official
distance is pool geometry only (ADR-036). `persistence` may import `swimcore.replay`;
`swimcore` never imports `persistence`. SQLite is a Faz 2 projection (ADR-003).

## Continuous pace curves & headless simulator (Commit 8, ADR-038)

A profile leg / official split duration is a **time constraint**; the within-length target
pace is carried by an approved **continuous curve**. `contracts/continuous_pace.py` adds
`ApprovedContinuousPaceProfile` (schema 1.1, `approved-pace-profile-1.1.json`) alongside the
unchanged 1.0 profile; `ApprovedPaceProfileVersion` is the union. Curves are **PCHIP**
(Fritsch–Carlson, `swimcore/pacing/pchip.py`, the only PCHIP in the tree, stdlib-only) for
native profiles or **CONSTANT_SPEED** for legacy migration and explicit templates; approved
knot speeds are strictly positive and finite.

`continuous_profile_compiler.py` compiles a 1.1 profile into the **existing** `PaceTimeline`
(no second ghost/time engine): deterministic breakpoints (knots ∪ phases ∪ locked splits ∪
walls ∪ a 0.10 m grid) → target speeds → `pace = 100/speed` → piecewise-linear
`PaceInterval`s → **exact total-time and locked-split reconciliation** (each locked region
scaled to its target, the remainder to `target − Σlocked`; reject, never clamp on negative
remainder / non-finite / non-positive speed / post-reconciliation bound violation). The
compiler recomputes an authoritative `CurveValidationSummary`; only `validationPassed` runs
live. Central constants: `CONTINUOUS_CURVE_MAX_STEP_M = 0.10`, `CURVE_TIME_TOLERANCE_SEC =
1e-6`. `continuous_migration.py` turns each legacy leg into a constant-speed segment + locked
split (pure, non-mutating, no smoothing — leg boundaries reproduce bit-identically).

Runtime is backward compatible: `select_live_pace_profile`, the aggregate profile registry
and `compile_live_profile` accept both versions; the **GhostClock is unchanged** (still
consumes a `PaceTimeline`). `CoachPacingReset.replacementPaceProfileRef` +
`GhostClock.apply_timeline_reset_at_wall` implement a **safe-wall** continuous-curve reset —
resolved/compiled atomically at request time, applied at the next official wall. It is **not**
a StopPause: no clock freeze, no `stoppedDuration`, prior splits/gap history preserved, ghost
wall-continuity kept. Planning ML (Phase-aware Conditional Transformer + Spline Decoder) is a
contract direction only — nothing is trained or run, and live runtime never calls it.

The **headless simulator** (`src/simulator/`) is a deterministic test harness that embeds the
**real** `SessionAggregate` + real `JsonlSessionEventLog` + real replay and duplicates no
domain logic (enforced by `tests/architecture/test_simulator_boundaries.py`). A splitmix64
virtual swimmer, eight failure scenarios, `SYNTHETIC_SIMULATION` provenance
(`usedRealHumanData=False`, `licenseVerified=False`) and a CLI (`swimtools.run_scenario`)
produce byte-identical journals for a given scenario. External-data records gain optional
continuous-curve columns (missingness preserved); `swimtools/swimming_features.py` holds pure
feature-extraction helpers; `ContinuousCurveReportContext` is an optional, not-yet-computed
report field (Commit 9).

## What is NOT here in Phase 1

`cloud/`, `ml/` runtime, `ui/`, device drivers, partner adapters, an SQL database / ORM /
WAL projection (the Commit 7 journal is plain append-only JSONL; SQLite is Faz 2, ADR-003),
FastAPI, wearable connectors, rule-based/ML adaptation engines. These arrive in later phases
with their own ADRs and triggers.

## Distance-specific approved pace profiles (mainline)

Live pacing consumes a single authoritative `ApprovedPaceProfile` (ADR-034). Legs cover the
distance with no gap/overlap and sum exactly to the target total time; the deterministic
compiler (`compile_approved_pace_profile`) produces a bit-identical timeline. Profile
selection is deterministic and honours the coach authority order
(`COACH_AUTHORED > COACH_APPROVED_MODEL > DEFAULT_MODEL_GENERATED`), with a coach lock that
blocks ML/rule auto-override. Workout 1.1 makes start mode and pool length mandatory
execution context; official distance comes only from workout geometry / verified walls, never
from a wearable estimate (ADR-036).

Runtime boundary: the deterministic core only *executes* an already-approved profile — it
never generates one and never calls model inference in the live loop. The pre-session
planning model (DRAFT profiles, gated by P1–P7) and the live adaptation model (gated by
G1–G7, behind the SafetyController) are separate and both optional (ADR-035).


## Dataset evidence layer (Commit 8 correction, ADR-039)

External research datasets sit **outside** the runtime and outside the repository:

```
data/external/raw/   gitignored local mount (operator-provided ZIP bundles)
data/catalog/*.json  checked-in DatasetAssetManifest records (hashes, counts, roles,
                     license, eligibility, restrictions, grouping keys, leakage rules)
data/schemas/*.json  checked-in per-dataset expectations
```

`swimtools.data_catalog` loads and gates the catalog (typed `DatasetEligibilityError` on a
production or primary-research request that the license/quarantine state forbids);
`swimtools.validate_dataset_bundle` validates a raw bundle with stdlib-only streaming
(`zipfile`, `csv`, `hashlib`) in bounded memory, rejecting zip-slip, duplicate and
unexpected members; `swimtools.data_splitting` provides pure leakage validators.

Boundaries (import-linter enforced): `swimcore` reads no dataset and never imports
`contracts.data_assets` or `contracts.forecasting`; `contracts` performs no I/O; the
simulator reads no dataset and performs no inference; no runtime `pandas`/`numpy`/`scipy`
dependency exists; `src/ml/` does not exist before Phase 5.

Scientific boundary: **measured instantaneous velocity ≠ operational target velocity
envelope**. A generated within-length shape is a bounded template or coarse latent shape,
stamped through `CurveProvenance` (`curveOrigin`, `curveEvidenceLevel`, `visualShapeSource`,
`continuousCurveGroundTruth = false`), and the coach target is never mutated by a forecast.

## Physical-bound verification (Commit 8 correction)

`swimcore/pacing/curve_bounds.py` verifies speed, gradient and acceleration bounds
analytically per PCHIP interval: speed extrema from the closed-form roots of `v'(t) = 0`,
gradient extrema from `v''(t) = 0`, and acceleration through a branch-and-bound whose
per-subinterval bound `|a| ≤ max|v| · max|dv/dd|` comes from those closed-form extrema. The
same verification runs after reconciliation with each region's pace scale factor applied;
`physicalBoundsChecked = true` is only written when that post-check passed. Sampling remains
corroboration, never proof.

---

## Commit 9 — Deterministic analytics and reporting (ADR-040)

The Phase-1 package graph now includes a pure `analytics` layer:

```text
swimtools > simulator > analytics > persistence > swimcore > contracts
```

`analytics` consumes `HistoricalSessionState`, typed event envelopes, workout/profile
contracts, compiled `PaceTimeline` and explicitly supplied trusted observations. It never
reads mutable live aggregate state, raw datasets or the filesystem, and it cannot import
simulator/persistence/swimtools. The journal remains authoritative; reports are separate,
canonical derived artifacts.

`SessionReport` 1.1 adds deterministic identity/provenance, timing and official-distance
summaries, per-wall target/actual split analysis, aggregate adherence, pacing shape/fade,
trusted continuous-curve deviation, StopPause and safe-wall reset histories, optional
advisory HR/stroke summaries and metric-availability statuses. The 1.0 contract/schema is
unchanged. Simulator invokes the public analytics API and verifies two builds from the same
journal produce identical bytes/hash.

Corrected Commit 9 treats report identity as content-addressed and records digests for the
workout, initial profile/timeline, reset profile registry, observations, sensors and analytics
policy. A coach-reset journal cannot be reported without the replacement profile/timeline
registry. Input geometry/profile coherence is validated before metrics are built. Trusted
observations are restricted to the session horizon; smoothed-velocity-only observations are
supported by deterministic integration without becoming official distance. Resolved
StopPause and completed wall reconciliation remain separate states.


---

## Commit 10 — Phase 1 vertical-slice verification (ADR-041)

The final Phase 1 package graph:

```text
swimtools > e2e > simulator > analytics > persistence > swimcore > contracts
```

`e2e` is an orchestration layer with no domain logic. `run_phase1_vertical_slice` compiles
the case plan with the production compiler, drives the production `SessionAggregate` through
the simulator harness onto the production `JsonlSessionEventLog`, then **re-reads the journal
from disk**, replays it with the production reducer and rebuilds the report through the
public analytics API — the rebuilt bytes must equal the bytes the runtime produced.

`e2e.verification` is the single authoritative cross-component invariant matrix (event,
state, clock, distance, profile, report and case-expectation groups). `e2e.manifest` emits a
canonical, content-addressed `Phase1VerificationManifest`. Each case writes a bundle of
`manifest.json`, `journal.jsonl`, `session-report.json`, `command-outcomes.json` and
`artifact-sha256.txt` (plus `observations.jsonl` when applicable), all canonical UTF-8 JSON
with LF endings and no absolute path, timestamp, UUID or raw dataset.

`swimtools.run_e2e` runs the matrix; `swimtools.verify_e2e_bundle` re-proves a bundle from
its bytes with typed exit codes (0 valid, 2 invalid input, 3 digest mismatch, 4 semantic
mismatch). Golden bundles under `tests/e2e/goldens/` are the release regression contract.

Determinism: `runId` and `manifestId` are content addressed; the output directory never
influences artifact bytes; no wall clock, randomness or network is used by the layer.
