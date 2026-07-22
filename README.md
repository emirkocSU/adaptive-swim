# Adaptive Swim Pacing Platform

Offline-first, hardware-independent adaptive swim pacing. A coach defines a structured
workout; the system drives a personal **ghost pacer** and produces an explainable
session-end target-vs-actual report. No LLM participates in the critical pacing path, and
the live core remains deterministic and offline.

## Phase 1 scope

This repository contains the headless Phase 1 vertical slice in Python. It deliberately
contains no cloud runtime, production ML package, UI, database projection or device driver.
Seven source packages live under `src/`:

- `contracts` — strict data contracts, enums, commands/events and generated JSON Schemas;
  no I/O.
- `swimcore` — pure domain logic: workout validation, pace math, ActiveClock/GhostClock,
  StopPause, session aggregate and safety control; no I/O or framework.
- `persistence` — append-only canonical JSONL journal, durability handling, replay inputs and
  the optional derived-report store; local file I/O only.
- `analytics` — pure replay-based SessionReport 1.1 calculations, provenance, identities and
  canonical serialization; no filesystem, wall clock, randomness, network or ML runtime.
- `simulator` — deterministic virtual swimmer and required failure scenarios; embeds the real
  `swimcore` rather than implementing a second pacing engine.
- `e2e` — full Phase 1 orchestration, migration-equivalence execution and canonical release
  bundles; owns no domain rules.
- `swimtools` — developer/CI CLIs for schemas, architecture, datasets, reports, E2E execution,
  bundle verification and mechanical Phase 1 completeness.

## Setup and verification

```bash
python -m pip install -e ".[dev]"
make phase1-completeness
make ci
```

Windows PowerShell users may run the individual Python/Ruff/Mypy/import-linter commands when
GNU Make is not installed.

Useful E2E commands:

```bash
python -m swimtools.run_e2e --list
python -m swimtools.run_e2e --case normal-continuous-completion --seed 42 --output ./out
python -m swimtools.run_e2e --all --output ./e2e-all
python -m swimtools.verify_e2e_bundle --bundle ./e2e-all --recursive
```

## Phase 1 correction release status

Commits 1–10 and their contracts are implemented. This correction release additionally
closes the following release blockers:

- failed commands restore both aggregate values and the original
  `ActiveClock -> GhostClock -> PaceTimeline` reference graph;
- simulator live-state reads use the aggregate's authoritative `activeClock`, not a harness
  workaround;
- run identity covers scenario version/content, source/runtime workout, every initial,
  replacement and equivalence profile, and analytics policy;
- the bundle verifier independently recomputes `runId`, `reportId` and `manifestId`;
- `manifestId` is transitively bound to journal, report, command outcomes, optional
  observations and the canonical digest file;
- legacy/migrated profile equivalence executes two real aggregate → journal → replay → report
  chains and compares timeline, command outcomes, journal semantics/batches, live state,
  replay state and report targets;
- the legacy E2E case starts from a real Workout 1.0 document and explicitly migrates it;
- `make phase1-completeness` mechanically rejects missing suites, unresolved invariant
  bindings, duplicate markers and temporary-success Makefile paths.

The package is marked **READY_FOR_OPERATOR_VALIDATION** because, at the user's request, the
final correction was prepared without running pytest, `make ci`, Ruff, Mypy or import-linter.
Run the commands above before committing or promoting the release.

## Phase status

| Commit | Scope | Implementation |
|---|---|---|
| 1 | Repository scaffold and architecture guards | present |
| 2 | Contracts and generated schemas | present |
| 3 | Semantic workout validation | present |
| 4 | Deterministic pace math | present |
| 5 | Active/ghost clocks | present |
| 6 | Session aggregate, StopPause and safety | present |
| 7 | Append-only journal and historical replay | present |
| 8 | Continuous pace profiles and deterministic simulator | present |
| 9 | Deterministic analytics and SessionReport 1.1 | present |
| 10 | Full vertical-slice verification and release bundles | present |

`PHASE1_RELEASE_MANIFEST.json` records the supported versions, canonical cases, excluded
scopes and the operator-validation status. Phase 2 remains coach tooling; later phases cover
pilot integration, data acquisition, production pacing ML and personalization.

See `CLAUDE.md` for non-negotiables, `ARCHITECTURE.md` for the living architecture and
`docs/adr/` for binding decisions.
