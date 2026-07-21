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

**Commit 8 complete — ready for Commit 9.** Commits 1–7 are done: contracts + schema
(Workout 1.0/1.1, `ApprovedPaceProfile` 1.0), semantic validator, pace math engine,
deterministic SimClock/ActiveClock/GhostClock, approved-profile selection + deterministic
compiler, start-mode resolution, official-distance authority, the session orchestration
layer (state machine, StopPause, coach pacing reset, split recording, SafetyController), and
the append-only JSONL event journal + deterministic historical replay (Commit 7).

Commit 8 adds the **continuous pace-curve** mainline integration and the **deterministic
headless simulator** (ADR-038):

- Approved split/leg durations are **time constraints**; continuous within-length pacing is
  represented by an **approved curve** (PCHIP native; CONSTANT_SPEED for legacy/templates).
- Planning ML is a **Phase-aware Conditional Transformer + Spline Decoder** — a contract
  direction only; no model is trained or run in Commit 8.
- **Live execution stays deterministic and model-free**: the curve is compiled to a
  `PaceTimeline` with exact total-time and locked-split reconciliation before the session,
  and the existing GhostClock consumes it unchanged.
- `ApprovedPaceProfile` 1.1 (`approved-pace-profile-1.1.json`), a pure 1.0→1.1 migration, a
  safe-wall coach continuous-curve reset, and eight deterministic failure scenarios that run
  the **real** core embedded (byte-identical journals; replay-verified).

Plan: Commit 7 — done · Commit 8 — done · Commit 9 (analytics/report) — pending · Commit 10
(full vertical-slice verification) — pending.

No real ML, no coach UI, no wearable connector in this scope — planning ML and live
adaptation ML are contract- and gate-level only (ADR-034/035/036/038).

See `CLAUDE.md` for the non-negotiables and dependency rules, `ARCHITECTURE.md` for the
living architecture summary, and `docs/adr/` for decisions.
