# Phase 1 — Commit Plan (living)

Ordered, human-approved commits. Each adds one layer; later layers stay PENDING until
their commit lands.

| Commit | Scope | Status |
|---|---|---|
| 1 | Repo scaffold, tooling, layering guard | done |
| 2 | Contracts + JSON Schema (structural), validation contracts | done |
| 3 | Pure semantic workout validator (`swimcore/workout/`), 12 rules | done |
| 4 | **Deterministic pace math engine (`swimcore/pacing/`)** — this commit | done |
| 5–6 | Runtime clocks (GhostClock/SimClock), StopPause runtime, session state machine | pending |
| 7+ | Event persistence, replay, simulator swimmer, analytics report | pending |
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
