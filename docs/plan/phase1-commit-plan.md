# Phase 1 — Commit Plan (living)

Ordered, human-approved commits. Commits 1–10 are implemented; historical planning text
inside commit-specific sections is retained only as development context.

**This table is the single authoritative status list for Phase 1.** No other table in this
document repeats or contradicts it.

| Commit | Scope | Status |
|---|---|---|
| 1 | Repo scaffold, tooling, layering guard | done |
| 2 | Contracts + JSON Schema (structural), validation contracts | done |
| 3 | Pure semantic workout validator (`swimcore/workout/`), 12 rules | done |
| 4 | Deterministic pace math engine (`swimcore/pacing/`) | done |
| 5 | Deterministic clocks (`swimcore/time/`) + ghost primitive (`swimcore/ghost/`) | done |
| 6 | Session state machine, command handling, StopPause orchestration, SafetyController | done |
| 7 | Append-only event journal + deterministic historical replay (ADR-037) | done |
| 8 | Continuous pace curves + deterministic headless simulator (ADR-038) **+ dataset evidence plan, catalog, validators and leakage guards (ADR-039)** | done |
| 9 | Incident-aware analytics / session report (ADR-040) | done |
| 10 | Full vertical-slice verification and release closure (ADR-041) | done |
| later | ML advisory (Phase 5A–5E), cloud, UI, device/wearable adapters | pending (own ADRs/triggers) |

## Commit 4 boundary (what it is and is not)

Commit 4 is **active-swimming pace mathematics only**. It compiles a workout into a
distance/active-time target pace timeline and answers two inverse queries
(time-at-distance, ghost-distance-at-active-time) plus wall-boundary helpers.

Explicitly **out of scope** here (later commits): session state machine, StopPause runtime
controller, GhostClock/SimClock, event persistence, replay, simulator swimmer, analytics
report, ML, UI, cloud, hardware/device/wearable adapters, database.

- Rest, StopPause, and real elapsed time are **not** in this timeline — it carries active
  swim time only.
- Ghost distance is computed against **active** time at this stage.
- Freezing the active clock during a StopPause is Commit 5–6 work.
- The coach pacing reset applies at the next valid wall, but its runtime behaviour is not
  written yet.
- In the `20.00 +15.00` display, the `20.00` (active) comes from this Commit 4 timeline;
  the `+15.00` (stopped) will come from later StopPause runtime accounting.

## Commit 5 boundary (what it is and is not)

Commit 5 adds **deterministic clock and ghost primitives only**: `SimClock` (manual,
bit-identical), `ActiveClock` (wall vs active time with retroactive StopPause freeze), and
`GhostClock` (drives the Commit-4 timeline, mid-pool alignment via an explicit anchor, wall
reconciliation of the temporary alignment). Ghost states are ACTIVE / STOP_PAUSED only.

Explicitly **out of scope** (later commits): full session state machine, command handling,
event generation/persistence, JSONL replay, automatic stop *detection*, wearable/IMU,
simulated swimmer, analytics/report, SafetyController, ML, UI, cloud, hardware adapter,
database. Commit 5 never *detects* a StopPause — it only applies an externally confirmed one.

## Commit 4/5 fix notes

- ActiveClock is a **monotonic runtime clock**, not an event store; it rejects historical
  queries. Historical replay is reconstructed from events in Commit 7.
- A StopPause resume may not precede its confirmation time.
- Wall reconciliation happens once, only at the first valid wall after the confirmed
  StopPause alignment (never on a normal pace loss / normal ACTIVE ghost).
- Commit 5 performs no workout length/set/repetition/split accounting.
- Display `20.00 +15.00`: `20.00` active, `+15.00` stopped, `35.00` wall.

## Commit 6 boundary (what it is and is not)

Commit 6 is the **session orchestration layer** (`swimcore/session/`, `swimcore/control/`):
session aggregate + state machine (CREATED/ARMED/RUNNING/PAUSED/COMPLETED/ABORTED), typed
command handling with idempotency, in-memory domain event generation, StopPause
orchestration, coach pacing reset (request/apply-at-next-wall), split recording/verification,
and the deterministic SafetyController that gates every pace change.

- StopPause is **not** a lifecycle state: the session stays RUNNING while the ghost is
  STOP_PAUSED and the active clock is frozen.
- Normal pace loss is not a StopPause; coach pacing reset is not a StopPause.
- A coach pacing reset applies only at the next valid wall boundary.
- The SafetyController is the mandatory gate for all pace changes; ML only suggests, and low
  confidence/quality falls back to the coach plan.
- Accounting: `active = ActiveClock`, `stopped = confirmed StopPause intervals`,
  `elapsed = active + stopped`.

Out of scope (later commits): JSONL persistence, event replay, filesystem, database, network,
cloud, UI/FastAPI, real simulator swimmer, wearable/sensor processing, ML runtime, analytics
report, hardware/LED adapter. Persistence and replay are Commit 7.

## Commit 6 correction pass (completed)

All Commit 6 correction invariants (session-id validation, exact-workout completion,
splitId vs official length, wall-bound splits, coach-reset ghost-anchor at wall, lifecycle
pause freeze, atomic command handling, forward-only event time, full SafetyContext
validation, coach/rule/ML pace-source rules, loss-less reason codes, StopPause metadata
preservation, current-interval block resolution) are implemented and covered by tests. CI is
green (386 tests).

## Mainline integration (completed, pre-Commit 7)

The distance-specific approved-pace-profile / Workout 1.1 start-mode / planning-ML mainline
integration is now implemented as a set of mainline corrections/backports *before* Commit 7
(historical Commit 1–10 numbering is unchanged):

- Workout 1.1 (`WorkoutTemplateV1_1`, `StartPolicy`, per-block/per-repeat overrides,
  `workoutGoal`) + explicit `migrate_workout_1_0_to_1_1` (start mode never guessed).
- `StartMode` taxonomy and deterministic resolution (repeat → block → default).
- `ApprovedPaceProfile` + `PaceProfileLeg` contract with exact target-time reconciliation;
  leg ≠ official split.
- Deterministic `select_live_pace_profile` (authority order, coach lock, opt-in default) and
  `compile_approved_pace_profile` (bit-identical timeline).
- Official-distance authority + wearable-estimate restrictions (ADR-036).
- SafetyController profile authority: `profileSource` / `profileCoachLocked` /
  current-profile-leg target; distinct `ML_CONFIDENCE_MISSING` / `DATA_QUALITY_MISSING` /
  `COACH_PROFILE_LOCKED` reasons; exhaustive reason-code mapping.
- Pace-profile lifecycle event contracts (§13) and report-context expansion (§20), defined
  now for forward-compatible persistence/replay.
- New semantic rule codes (§21) and ADR-034/035/036.

No real ML, UI, wearable connector, or analytics implementation is added in this pass.

## Commit 7 (append-only event journal + deterministic replay) — completed

Commit 7 is implemented and covered by tests (ADR-037):

- `contracts.event_log.EventBatchRecord` (one command = one canonical JSONL line) with the
  generated schema `event-batch-record-1.0.json`; `SessionRecovered` gains its typed
  payload.
- `persistence` package: canonical byte codec, `JsonlSessionEventLog` (append-only,
  fsync-per-command-batch, parent-dir sync on create, partial-write/EINTR-safe loop,
  exact-duplicate idempotency, durability-uncertain retry, explicit tail recovery —
  torn-tail truncation vs missing-newline repair, middle corruption never skipped), and the
  explicit `build_session_recovered_event` helper.
- `swimcore.replay` package: pure `replay_session` folding events into
  `HistoricalSessionState`, reusing the authoritative transition table; separate
  active/stopped/lifecycle-paused/elapsed/wall duration axes with enforced invariants;
  retroactive StopPause start from payload; official distance from geometry only.
- Three byte-deterministic golden journals (`tests/replay/goldens/`), property invariants
  (`tests/property/test_replay_invariants.py`), and boundary tests
  (`tests/architecture/test_replay_boundaries.py`). `make test-replay` is a real target.
- SQLite remains a Faz 2 projection (ADR-003); no DB/web/network in Commit 7.

## Commit 8 (continuous pace curves + deterministic headless simulator) — completed

Commit 8 is implemented and covered by tests (ADR-038):

- `ApprovedPaceProfile` **1.1** (`approved-pace-profile-1.1.json`): a leg/split duration is a
  time constraint, within-length pace is an approved PCHIP (or CONSTANT_SPEED) curve. The 1.0
  contract and schema are unchanged.
- Pure Fritsch–Carlson PCHIP + deterministic compiler with **exact total-time and
  locked-split reconciliation** (reject, not clamp) reusing the existing `PaceTimeline`; pure
  1.0→1.1 migration (no smoothing).
- Backward-compatible runtime (both versions selectable/compilable; GhostClock unchanged) and
  a **safe-wall coach continuous-curve reset** (not a StopPause).
- Optional continuous-curve external-data fields, pure feature-extraction helpers, and a
  `ContinuousCurveReportContext` (contract only).
- A **deterministic headless simulator** embedding the real core: 8 failure scenarios,
  splitmix64 virtual swimmer, provenance, `swimtools.run_scenario` CLI, byte-identical
  journals, 3 committed simulator goldens; `make test-simulator` is a real target.
- Planning ML is contract direction only; nothing is trained or run, and the live runtime
  never calls it.

### Commit 8 acceptance correction (ADR-039)

The acceptance review of the first Commit 8 delivery found blocking gaps; they are closed:

- The **eight required failure scenarios** now exist under their exact slugs
  (`normal-pace-loss`, `long-stop-mid-length`, `manual-stop-at-verified-wall`,
  `duplicate-stop-mark`, `stop-during-planned-rest`, `unreliable-position-time`,
  `complete-while-stop-paused`, `coach-continuous-curve-reset`) and are no longer aliases of
  demo scenarios.
- `--seed` reaches the real virtual-swimmer RNG; the swimmer is a **tick-based** simulation
  producing per-tick observations with interpolated wall crossings.
- The harness re-reads its own journal, replays it, and fails the run on any live/replay
  mismatch; `SimulationResult` carries commands, outcomes, events, batches, observations,
  ghost snapshots, journal SHA-256, live state, replay result and a deterministic run
  manifest.
- The safe-wall coach reset now swaps **all** profile metadata (id, version, source, type,
  coach lock, applied pace, target total time, curve representation, compiler version) in
  the live aggregate *and* in historical replay.
- All physical bounds are re-verified after reconciliation at the reconciled scale, using
  **analytic** PCHIP critical points rather than a sampling grid.
- `+inf` / `-inf` / `NaN` are rejected at the contract boundary.
- The dataset catalog, streaming validator, license/quarantine gates, leakage guards,
  feature helpers, curve-evidence provenance and the Phase 5A–5E roadmap landed (ADR-039).

Historical Commit 9 note: deterministic analytics/report implementation and ten critical correctness fixes landed under ADR-040, but that delivery did not claim full clean-CI acceptance. Commit 10 and the final correction supersede that status.

## Roadmap phases (updated for the mainline)

- **Phase 1 (now):** Workout 1.1 start-mode contracts; approved pace-profile contracts;
  deterministic profile selection/compilation/execution; official-distance safety;
  Session/Safety integration. No real ML, no UI, no wearable connector.
- **Phase 2:** coach workout form; visual pace-profile editor; manual/template/generate-edit
  workflows; local profile approval/locking; optional planning model only if P1–P7 passes.
- **Phase 3 — Pool Pilot 0:** coach-authored/approved fixed profiles; 25 m vs 50 m behavior;
  official distance & wall validation; no live adaptive ML claim.
- **Phase 4:** consented wearable/import data; start/turn/HR metadata; personal calibration
  dataset; coach feedback capture.
- **Phase 5:** deterministic rule-based adaptation; planning model shadow/generate-edit
  evaluation; personal calibration experiments; coach remains final authority.
- **Phase 6:** live adaptation ML only if the existing G1–G7 gate passes; planning and
  adaptation models evaluated separately.
- **Phase 7+:** comparative pilots, cloud, OEM per the existing roadmap.

## Commit 9 completion scope

Commit 9 adds the pure analytics package, SessionReport 1.1, canonical identity/serialization,
official split/distance and pacing analysis, trusted curve and optional sensor summaries,
StopPause/reset provenance, report CLIs/store, simulator reports and golden/property tests.
It adds no live adaptation, model training, cloud, UI or device integration. Commit 10 subsequently closed the vertical slice; this paragraph is retained as historical Commit 9 scope.


## Commit 10 (Phase 1 vertical-slice verification and release closure) — completed

Commit 10 adds verification, not behaviour (ADR-041):

- `src/e2e/` orchestrates the whole authoritative chain with the **real** components and
  re-reads its own journal to rebuild the report through the public analytics API; the two
  independently produced reports must be byte-identical.
- Thirteen vertical-slice cases: the ten required closure cases plus the three remaining
  required failure scenarios, so all eight Commit 8 scenarios now also produce reports end to
  end. Each case proves 85–91 cross-component invariants.
- One authoritative invariant matrix (`e2e.verification`) covering event, state, clock,
  distance, profile, report and case-expectation groups, with explicit `NOT_APPLICABLE`
  results where a check cannot apply.
- Content-addressed `runId` and `manifestId`; canonical bundles (`manifest.json`,
  `journal.jsonl`, `session-report.json`, `command-outcomes.json`, `artifact-sha256.txt`,
  optional `observations.jsonl`) with no path, timestamp, UUID or dataset content.
- `swimtools.run_e2e` and `swimtools.verify_e2e_bundle` (typed exit codes 0/2/3/4); real
  `make test-e2e` and `make e2e-headless`, both inside `make ci`.
- Five committed golden bundles as the release regression contract, plus
  `PHASE1_RELEASE_MANIFEST.json`.

**Phase 1 implementation is complete and requires operator validation for this packaged correction.** Phase 2 (coach tooling) is the next product phase; Phase 5 remains the first phase in which a real model is trained.
