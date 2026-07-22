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
- `swimtools` — developer/CI CLIs (schema generation, scenario runner, arch checks, dataset
  catalog + streaming bundle validator, leakage guards, pure feature helpers).

## 60-second headless session (target, wired up by Commit 10)

```bash
make setup
make ci            # lint, typecheck, arch, schema-check, unit (+ later: property/replay/sim/e2e)
```

## Current status

**Commit 8 corrected v2: real dataset integration complete.** The simulator, continuous
curve, safe-wall reset, deterministic seed/replay and core architecture remain unchanged.
This correction is limited to raw dataset contracts, catalog/schema metadata, validator
behavior, tests and documentation.

All four supplied bundles pass the streaming validator:

| Bundle | Structural result | Policy result |
|---|---|---|
| official race | VALID — 128,475 rows × 151 columns | `RACE_PACING_PRIOR`, license TBD → production blocked, curve ground truth false |
| IMU | VALID — 40,957 × 94 | sensor/technique research; not primary pacing target; not official distance |
| training/fatigue | VALID — 396 × 111 | real `record_granularity`: 228 `ATHLETE_WEEK`, 168 `SPRINT_REPEAT`; mixed license |
| external studies | VALID — seven exact members | controlled research; massage condition-aware; stroke file `SMOKE_TEST_ONLY` |

Raw headers are validated as supplied. Canonical `subject_uid`, `session_uid` and
`record_type` are created only by explicit normalized mappings; they are not invented raw
requirements. The external-studies ZIP is validated once, while the stroke member keeps its
file-level quarantine gate. Raw dataset files are not included in this repository.

The dataset correction does not modify `swimcore`, simulator, persistence, replay fixtures or
simulator fixtures. Those trees are byte-identical to the supplied corrected baseline; the
direct replay and simulator regression suites pass (131 and 109 tests respectively). See
`IMPLEMENTATION_REPORT.md` for the exact command matrix and sandbox tool-availability notes.

The product claim remains: race/research/training distributions and corrections produce a
smooth, feasible operational target velocity envelope that exactly matches target time and
splits — not measured instantaneous velocity ground truth.

**Final decision: `READY_FOR_COMMIT_9`.**

Plan: Commit 7 — done · Commit 8 — done/corrected · Commit 9 (analytics/model training) —
pending. No Commit 9 analytics or real ML training is included.

## Validating a dataset bundle (operator step, outside CI)

```bash
python -m swimtools.validate_dataset_bundle --all --data-root data/external/raw
python -m swimtools.validate_dataset_bundle --bundle /path/to/bundle.zip --format json
```

See `CLAUDE.md` for the non-negotiables and dependency rules, `ARCHITECTURE.md` for the
living architecture summary, and `docs/adr/` for decisions.
