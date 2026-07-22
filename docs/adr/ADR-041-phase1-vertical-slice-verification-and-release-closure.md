# ADR-041 — Phase 1 Vertical-Slice Verification and Release Closure

- **Status:** Accepted, corrected
- **Date:** 22 July 2026
- **Scope:** Phase 1 verification, release identity, rollback atomicity and migration evidence
- **Supersedes:** the rollback deferral and partial release-integrity wording in the first
  ADR-041 draft

## Context

Phase 1 already had deterministic domain logic, continuous pace profiles, an embedded-core
simulator, append-only event persistence, replay and derived analytics. Closing the phase
requires more than proving that each package works separately. A release must demonstrate
that the real aggregate, journal, replay and report agree; that failed commands leave the
aggregate unchanged; that legacy migrations preserve complete session behaviour; and that a
bundle identity changes whenever any deterministic input or emitted payload changes.

The first closure draft had four gaps:

1. rollback restored equal clock values but could detach the shared
   `ActiveClock -> GhostClock` reference;
2. `runId` omitted replacement profiles and analytics policy;
3. manifest verification did not recompute `runId` or bind outcomes/observations;
4. migration equivalence compiled a partner profile but did not execute a second real
   session.

These are Phase 1 correctness requirements, not Phase 2 enhancements.

## Decision

### 1. Commit 10 remains verification, not a product feature

The E2E layer orchestrates existing real components and owns no workout, pacing, clock,
session, replay or analytics rule. No UI, device driver, cloud service or production ML
runtime is introduced.

### 2. Failed commands are atomically invisible

Before a command, `SessionAggregate` captures:

- the original references of all mutable aggregate fields;
- one deep-copied checkpoint graph, preserving internal aliases;
- the event-factory checkpoint.

On failure, dictionaries and clock objects are restored in place. `GhostClock` is explicitly
rebound to the aggregate's exact `activeClock` and `paceTimeline`, and the aggregate asserts
this identity relation after rollback, successful commands and idempotent retries.

Therefore “aggregate unchanged” includes both values and object-reference topology. The
simulator reads live timing from `aggregate.activeClock`; it may not work around a detached
aggregate by reading a private clock through `ghostClock`.

### 3. Real components only

One E2E case drives:

```text
Workout contract/migration
  -> approved-profile selection and compiler
  -> SessionAggregate
  -> command outcomes and domain events
  -> append-only canonical JSONL journal
  -> journal re-read and historical replay
  -> replay-based SessionReport 1.1
  -> canonical release bundle and verifier
```

The report rebuilt from the persisted journal through the public analytics API must match
the simulator-produced report bytes.

### 4. Deterministic run identity covers every effective input

The E2E `runId` is SHA-256 over canonical material containing:

- case id/version and seed;
- runner version;
- source Workout 1.0 digest, when present;
- runtime Workout 1.1 digest;
- scenario version and canonical scenario digest;
- every initial, replacement and equivalence profile digest;
- selected profile id/version;
- replacement profile id/version;
- effective analytics-policy digest.

The simulator run identity follows the same principle with its simulator/harness versions.
No path, current timestamp, UUID or output directory enters either identity.

The bundle verifier recomputes `runId` from manifest fields rather than trusting the stored
value.

### 5. Canonical payload chain and manifest identity

A full bundle contains:

```text
journal.jsonl
session-report.json
command-outcomes.json
observations.jsonl        # optional, case-declared
artifact-sha256.txt
manifest.json
```

All JSON is UTF-8, sorted-key, compact, finite-only and LF-terminated where the format uses
lines. The verifier rejects pretty/non-canonical encodings, CRLF and unexpected files.

`artifact-sha256.txt` records every payload digest except `manifest.json`. The manifest
records the same payload-digest map and the SHA-256 of `artifact-sha256.txt`, plus direct
journal/report digests. `manifestId` is SHA-256 over the canonical manifest with only
`manifestId` omitted.

Thus any changed payload byte requires an updated digest file and manifest, which changes
`manifestId`. Any changed manifest field also changes `manifestId`. This provides complete
content binding; publisher authenticity would require a future signature layer.

The verifier independently recomputes payload hashes, `runId`, `reportId` and `manifestId`.

### 6. One authoritative invariant matrix

The E2E manifest records structured checks for:

- event sequence, IDs, timestamps and command-batch structure;
- rejected-command atomicity and idempotent retry;
- live aggregate vs historical replay state;
- active/stopped/elapsed/lifecycle-paused timing axes;
- official pool-wall distance authority;
- selected/replacement profile authority and exact reconciliation;
- report provenance, canonical bytes, content identity and missing-data semantics;
- case-specific StopPause, reset, evidence and observation expectations;
- full migration equivalence when declared.

The manifest group flags are derived from these checks, not maintained independently.

### 7. Migration equivalence requires two complete sessions

For a profile 1.0 and its migrated profile 1.1 counterpart, the runner executes two real
aggregate/journal/replay/report chains under the same workout, seed and swimmer parameters.

Equivalence covers:

- total duration/distance and coverage;
- sampled target function and official wall targets;
- command outcomes;
- journal event semantics and batch shape;
- live aggregate output;
- replay state;
- report timing/distance/split projection;
- report split targets.

Only schema/compiler representation metadata may differ. Merely compiling the partner
profile is insufficient.

### 8. Workout 1.0 compatibility is exercised end to end

The legacy compatibility case begins with a real Workout 1.0 object. The runner explicitly
migrates it using declared start-mode and workout-goal context, checks the migrated digest
against the runtime Workout 1.1, then executes the full chain with an approved profile 1.0.

### 9. Mechanical completeness is a CI prerequisite

`python -m swimtools.completeness_check` and `make phase1-completeness` verify repository
structure without executing tests. The check fails for missing suites/tools, unresolved
I-P1-01…20 bindings, duplicate pytest markers, Makefile `PENDING` fallbacks, conditional
property-test success or a `ci` target that omits the completeness gate.

`make ci` depends on this gate and runs real property/E2E targets directly.

### 10. Official distance and clock authority are unchanged

Only workout geometry and official wall events establish official distance. Observations,
wearables and integrated velocity remain analytical only. StopPause affects the active
clock according to its existing rules; normal pace loss and coach pacing reset do not create
stopped time.

### 11. Dataset boundary is unchanged

Raw external datasets are not included in runtime or release bundles. Dataset evidence is
provenance, not session performance evidence. Synthetic simulation remains explicitly
marked and cannot support a real sporting-performance claim.

## Consequences

### Positive

- rejected commands cannot leave a detached live clock graph;
- live state is the aggregate state, not a simulator workaround;
- replacement profile and policy changes produce different run identities;
- outcomes and optional observations participate in release identity;
- verification can reconstruct every identity from bundle contents;
- migration compatibility is supported by real persisted-session evidence;
- Phase 1 cannot report green through a missing-suite `PENDING` path.

### Costs

- manifest and runner contracts advance to version 1.1;
- previous E2E/report goldens must be regenerated because deterministic identities change;
- migration-equivalence cases run two sessions and therefore cost more test time;
- a content-bound manifest is not a publisher signature; signed distribution remains future
  work.

## Validation obligations

The repository includes tests for:

- runtime reference-graph preservation after rejected commands;
- run-id sensitivity to replacement profiles and analytics policy;
- verifier-side run-id recomputation;
- outcomes/observations payload binding;
- real Workout 1.0 E2E migration;
- dual-session migration equivalence;
- mechanical Phase 1 completeness;
- canonical full-bundle goldens.

The final correction package is intentionally marked `READY_FOR_OPERATOR_VALIDATION`: these
included tests must be run by the operator before release promotion.
