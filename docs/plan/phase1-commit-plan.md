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
| 6 | Session state machine, command handling, StopPause runtime, SafetyController | pending |
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
