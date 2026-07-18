# Adaptive Swim Pacing Platform

Offline-first, hardware-independent adaptive swim pacing. A coach defines a structured
workout; the system drives a personal **ghost pacer** and, session-end, produces an
explainable target-vs-actual report — with no LLM in the critical path and the live
pacing loop running fully offline.

## Phase 1 scope (this repository)

Headless core vertical slice, in pure Python. **No** cloud, ML runtime, UI, database, or
device driver. Five source packages under `src/`:

- `contracts` — data contracts, enums, event envelope, commands; single source of the
  JSON Schemas. No I/O.
- `swimcore` — pure domain logic (validation, pace math, ghost + StopPause, session
  state, safety controller, analytics). No I/O, no framework.
- `persistence` — append-only JSONL log + deterministic replay. Local file I/O only.
- `simulator` — virtual swimmer + scenarios; runs the real `swimcore` embedded.
- `swimtools` — developer/CI CLIs (schema generation, scenario runner, arch checks).

## 60-second headless session (target, wired up by Commit 10)

```bash
make setup
make ci            # lint, typecheck, arch, schema-check, unit (+ later: property/replay/sim/e2e)
```

## Current status

Commit 6 complete (incl. correction invariants). The distance-specific pace-profile / Workout 1.1 start-mode / planning-ML mainline integration is pending its authoritative source document and is not yet done. Contracts + schema, semantic validator, pace math
engine, deterministic SimClock/ActiveClock/GhostClock, and the session orchestration layer
(state machine, command handling, StopPause orchestration, coach pacing reset, split
recording/verification, and the mandatory SafetyController) are in place. Later commits add
pace math, ghost/StopPause state, event log + replay, simulator, and the full
network-disabled end-to-end slice.

See `CLAUDE.md` for the non-negotiables and dependency rules, `ARCHITECTURE.md` for the
living architecture summary, and `docs/adr/` for decisions.
