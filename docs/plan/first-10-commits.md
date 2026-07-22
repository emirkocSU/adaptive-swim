# Phase 1 — First 10 Commits

This file is the historical ordered commit plan. References to `PENDING` describe temporary
states allowed before Commit 10; they are not the current repository status.

1. **Repository scaffold and architecture anchors** — tooling, ADR-031/032/033, docs,
   architecture tests and the planned completeness gate.
2. **Core contracts and workout schema** — generated JSON Schema and golden examples.
3. **Semantic workout validator** — Workout 1.1 semantic rules.
4. **Pace math pure functions** — four modes and analytic checks.
5. **Clocks and ghost math** — injected clock/id ports, ActiveClock, StopPause accounting,
   controlled alignment and wall reconciliation.
6. **Session state machine, timing sub-state, StopPause events and safety controller** —
   deterministic command handling and bounded controller table.
7. **Append-only event log and replay** — canonical command-batch JSONL, durability,
   recovery and pure historical replay.
8. **Headless simulator and failure scenarios** — deterministic swimmer, continuous profile,
   StopPause, pace loss, duplicate command, planned rest, unreliable observation and coach
   reset scenarios.
9. **Deterministic analytics and SessionReport 1.1** — timing/distance/split/curve/advisory
   analytics, canonical report identity and canonical report store.
10. **Full vertical-slice verification and release closure** — real aggregate → journal →
    replay → report chain, content-addressed bundles, full migration equivalence, mechanical
    completeness and release manifest.

## Historical status notes

- The original Commit 8/9 delivery reports contained `BLOCKERS_REMAIN` because their full
  configured tool matrices had not been executed in those delivery environments.
- The original Commit 10 draft deferred aggregate clock-alias rollback to Phase 2 and used a
  narrower run/bundle identity contract. Those statements are superseded by the corrected
  ADR-041 and the final correction delta.

## Current implementation state

Commits 1–10 are implemented. The final correction includes:

- atomic rollback preserving the shared ActiveClock/GhostClock/PaceTimeline reference graph;
- run identity coverage for Workout 1.0 source, all profile digests, replacement profile,
  scenario digest and analytics policy;
- verifier-side runId recomputation;
- manifest binding of command outcomes, optional observations and the digest file;
- two full runtime chains for legacy/migrated profile equivalence;
- a real Workout 1.0 legacy compatibility e2e case;
- `swimtools.completeness_check` and `make phase1-completeness`;
- no Makefile PENDING-success path and no duplicate pytest marker.

The correction delivery intentionally does not claim a fresh green test run. The operator
must run the supplied CI commands before marking the release validated.
