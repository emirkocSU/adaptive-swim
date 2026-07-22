# IMPLEMENTATION REPORT — Adaptive Swim Phase 1 final correction candidate

**Baseline:** `adaptive-swim-phase1-complete-full.zip`
**Correction status:** `READY_FOR_OPERATOR_VALIDATION`
**Test-execution policy:** No pytest suite, `make ci`, Ruff, Mypy or import-linter command was
run while preparing this correction, as explicitly requested by the user.

## 1. Purpose

This correction closes the remaining Phase 1 release-integrity gaps without adding Phase 2
product behaviour. Coach authority, official-distance authority, deterministic runtime,
Workout 1.0/1.1 compatibility, approved-profile 1.0/1.1 compatibility, append-only journal,
historical replay and SessionReport 1.1 remain intact.

## 2. Atomic aggregate rollback

The previous rollback checkpoint deep-copied mutable fields independently. Because
`GhostClock` holds references to the aggregate's authoritative `ActiveClock` and
`PaceTimeline`, a rejected command could restore equal values while silently detaching the
runtime reference graph.

`SessionAggregate` now:

1. captures original mutable object references;
2. deep-copies the complete checkpoint mapping as one graph, preserving aliases;
3. restores aggregate dictionaries in place;
4. restores `ActiveClock` and `GhostClock` state in place rather than swapping objects;
5. explicitly rebinds `GhostClock` to the aggregate's exact `activeClock` and `paceTimeline`;
6. checks reference integrity after every successful command, idempotent retry and rollback.

The simulator harness no longer reads live clock totals through `ghostClock`. It reads the
actual aggregate `activeClock`, so the reported live state is the authoritative aggregate
state rather than a workaround.

A regression test records the three original runtime identities, triggers a rejected
command and asserts value equality, identity equality and graph binding after rollback.

## 3. Deterministic run identity

Both simulator and E2E run identities now cover every declared deterministic input capable
of changing runtime or report output:

- scenario id, version and canonical digest;
- seed and runner/harness version;
- source Workout 1.0 digest when applicable;
- migrated/runtime Workout digest;
- all declared profile digests;
- selected profile id/version;
- coach-reset replacement profile id/version and digest;
- migration-equivalence source profile digest;
- effective analytics-policy digest.

Changing a replacement profile or analytics threshold therefore changes `runId` even when
the initial journal plan remains otherwise identical.

## 4. Release-bundle integrity

The Phase 1 manifest contract is version `1.1` and records the scenario identity, complete
profile identities/digests, analytics-policy digest and source-workout digest required to
recompute `runId`.

The canonical payload set is:

```text
journal.jsonl
session-report.json
command-outcomes.json
observations.jsonl        # only when emitted by the case
artifact-sha256.txt
manifest.json
```

`artifact-sha256.txt` binds every payload artifact except `manifest.json`, avoiding a
circular hash. `manifest.json` records both the measured payload digest map and the digest
of `artifact-sha256.txt`. `manifestId` is the canonical hash of the full manifest with only
its own id omitted. Consequently, a changed payload byte requires a new digest file and a
new manifest, which necessarily changes `manifestId`.

The verifier independently:

- enforces exact bundle membership;
- rejects non-canonical JSON/JSONL and CRLF content;
- measures every payload digest;
- checks the digest file and manifest digest map;
- recomputes `runId`, `reportId` and `manifestId`;
- checks selected/replacement profile identities against the manifest digest registry;
- verifies journal/report/session semantics and command-outcome persistence rules.

This is content integrity, not cryptographic publisher authentication; signing remains a
future distribution concern.

## 5. Full migration equivalence

The `migrated-profile-equivalence` case now executes two complete real chains with the same
workout, seed and swimmer parameters:

```text
legacy profile 1.0  -> aggregate -> journal -> replay -> report
migrated profile 1.1 -> aggregate -> journal -> replay -> report
```

The verification matrix compares:

- total time, total distance and coverage;
- sampled target function and every official wall target;
- accepted/rejected command outcomes;
- normalized event/journal semantics;
- command-batch sequence structure;
- live aggregate final state;
- historical replay state;
- report timing/distance/split projection;
- every report split target.

Only representation-specific schema/compiler metadata is normalized away. A second compile
without a second session is no longer considered sufficient evidence.

## 6. Real Workout 1.0 E2E source

`legacy-profile-compatibility` now starts from an actual `WorkoutTemplateV1_0`, explicitly
migrates it with the required start-mode and workout-goal context, verifies the migrated
digest against the declared runtime Workout 1.1, and then runs the complete E2E chain with
an approved profile 1.0.

## 7. Mechanical Phase 1 completeness

Added `src/swimtools/completeness_check.py` and the Makefile target:

```bash
make phase1-completeness
```

The checker does not execute tests. It rejects a repository when:

- any required suite is missing or contains no `test_*.py` file;
- schema/completeness tools are missing;
- Makefile contains a `PENDING` fallback;
- `ci` does not depend on `phase1-completeness`;
- property tests are conditionally skipped with a successful result;
- pytest markers are duplicated;
- the twenty documented invariant bindings are missing, duplicated, unparsable or point to
  a nonexistent test function.

`make ci` now runs real property and E2E targets directly and has no temporary-success path.

## 8. Documentation and configuration consistency

- duplicate `e2e` marker definitions and stale “later commits” marker descriptions were
  removed from `pyproject.toml`;
- Phase 1 status documents now distinguish historical Commit 9 evidence from the current
  correction candidate;
- the obsolete Phase 2 rollback deferral was removed;
- ADR-041 now treats atomic rollback, complete run identity, payload-bound manifests and
  full migration equivalence as Phase 1 requirements;
- release component versions were advanced to E2E runner `1.1.0` and verification manifest
  `1.1`.

## 9. Regression coverage added or strengthened

- failed-command runtime reference graph preservation;
- run-id sensitivity to replacement profiles and analytics policy;
- verifier-side run-id recomputation;
- command-outcome and observation payload binding;
- real Workout 1.0 E2E execution;
- full dual-session migration equivalence;
- mechanical repository completeness;
- full canonical golden bundle membership.

These tests are included in the repository but were not executed during this packaging pass.

## 10. Operator validation commands

Run from the repository root after installing development dependencies:

```bash
python -m pip install -e ".[dev]"
make phase1-completeness
make ci
```

Windows PowerShell without GNU Make should execute the equivalent individual commands for
Ruff, formatting, Mypy, import-linter, architecture, schema, unit, property, replay,
simulator, analytics and E2E verification.

## 11. Delivery decision

```text
READY_FOR_OPERATOR_VALIDATION
```

The reported implementation gaps are addressed in code, tests, ADRs and release metadata.
Promotion to a tested Phase 1 release must occur only after the operator runs the configured
CI matrix and reviews the result.
