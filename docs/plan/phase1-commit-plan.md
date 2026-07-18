# Phase 1 — Commit Plan (living)

Ordered, human-approved commits. Each adds one layer; later layers stay PENDING until
their commit lands.

| Commit | Scope | Status |
|---|---|---|
| 1 | Repo scaffold, tooling, layering guard | done |
| 2 | Contracts + JSON Schema (structural), validation contracts | done |
| 3 | Pure semantic workout validator (`swimcore/workout/`), 12 rules | done |
| 4 | **Deterministic pace math engine (`swimcore/pacing/`)** — this commit | done |
| 5 | **Deterministic clocks (`swimcore/time/`) + ghost primitive (`swimcore/ghost/`)** — this commit | done |
| 6 | **Session state machine, command handling, StopPause orchestration, SafetyController** — this commit | done |
| 7 | Event persistence + **historical replay** (rebuilt from events, not the runtime clock) | pending |
| 8+ | Simulator swimmer, analytics report | pending |
| later | ML advisory, cloud, UI, device/wearable adapters | pending (own ADRs/triggers) |

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

## Pending mainline integration (NOT in this pass)

The distance-specific approved-pace-profile / Workout 1.1 start-mode / planning-ML mainline
integration (start-mode taxonomy, ApprovedPaceProfile leg contract, deterministic
distance-specific profile compilation, P1–P7 planning-model gate, reporting-contract
expansion, the new semantic rule codes, and ADR-034/035/036) depends on the authoritative
source document `Adaptive_Swim_Model_Tabanli_Tempo_ve_Baslangic_Guncellemesi_TR.md`, which was
not available in this pass. These remain to be implemented once that document is provided, so
the mainline contract/core integration is not yet complete.
