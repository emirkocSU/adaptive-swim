# ADR-038 — Continuous Pace Curves and Phase-Aware Model Generation

- **Status:** ACTIVE (Faz 1, Commit 8)
- **Date:** 2026-07-20
- **Related / extends:** ADR-034 (distance-specific approved pace profiles — authority,
  approval, source priority and coach-lock kept; its constant-leg *execution* is extended
  and partially superseded here), ADR-031 (StopPause), ADR-036 (official-distance
  authority), ADR-037 (event journal & replay — unchanged), ADR-032 (external-data
  provenance)

## Context / Problem

In `ApprovedPaceProfile` 1.0 a leg is `legDistance + legDuration = a single constant average
pace across the leg`. That model cannot express what actually happens inside a length: a
dive/underwater phase, a breakout, surface swimming, a wall approach, a turn and a finish
each have very different speeds. Coaches and (later) planning models need to shape the
*within-length* target while still honouring official split/total time constraints.

## Decision

### A profile leg / split duration is a time constraint, not constant speed

An official split or profile-leg duration is the **time budget** for that distance span. The
within-length pace is carried by an approved **continuous target-speed curve**. 1.0 stays a
valid, bit-identical contract for backward compatibility; it is no longer the only pacing
model.

### Curve representation (PCHIP authoritative; CONSTANT_SPEED for legacy/templates)

Phase 1 supports two representations only: **PCHIP** (Fritsch–Carlson shape-preserving
monotone cubic Hermite — the authoritative native representation) and **CONSTANT_SPEED**
(legacy migration and explicit templates). No generic unbounded cubic spline. Curve knots
carry a strictly-positive, finite *speed* (m/s); a live/approved profile forbids zero or
negative speed. A raw planning `0 m/s @ 0 m` start value is a *planning* artifact, never an
approved live curve — Commit 8 does not create a singular `1/velocity` integral; a true
start-from-rest primitive is deferred.

### Phase taxonomy

A within-length phase (`ContinuousPacePhaseType`: start-acceleration, start-underwater,
breakout, surface, mid-length, wall-approach, turn-entry/transition/underwater,
final-acceleration, finish, custom) is an **analytical span**, never an official wall
boundary and never an official split. The 1.0 `PaceProfilePhase` enum is untouched.

### Planning architecture (contract only in Commit 8)

`coach/model target total time → Phase-aware Conditional Transformer → Spline Decoder →
exact target-time reconciliation → coach approval / lock → approved continuous profile →
deterministic compiler → precomputed PaceTimeline → GhostClock`. Commit 8 implements the
contract, curve math, deterministic compiler, runtime execution and simulator — **no
Transformer is trained and no inference is run**. Live runtime never calls planning ML.

### Deterministic compilation (reuse the existing timeline engine)

The compiler reuses the existing `PaceTimeline` / `PaceInterval` /
`target_active_time_at_distance` / `ghost_distance_at_active_time`. No second ghost or
time↔distance engine, no second PCHIP. Pipeline: validate curve → deterministic breakpoints
(knots ∪ phase ∪ locked-split ∪ wall boundaries ∪ `0`/`total` ∪ uniform max-step grid) →
evaluate target speeds → `pace = 100 / speed` → piecewise-linear `PaceInterval`s → exact
reconciliation → `PaceTimeline`. The sampling step is one central constant,
`CONTINUOUS_CURVE_MAX_STEP_M = 0.10 m`; it bounds the piecewise-linear inverse-query error
far below the time tolerance for realistic pool speeds and is proven by the inverse-query
tests.

### Exact target-time and locked-split reconciliation

Because a `PaceInterval`'s duration scales linearly with pace, each locked-split region is
scaled independently to its target (`newPace = oldPace × target/current`, i.e.
`newVelocity = oldVelocity / factor`), then the unlocked remainder is scaled by a single
factor to `targetTotal − Σ lockedTargets`. Locked-split targets are never modified; the
total is never silently changed. Negative remaining time, non-finite or non-positive speeds,
or a post-reconciliation physical-bound violation cause **rejection, never clamping**. The
central tolerance is `CURVE_TIME_TOLERANCE_SEC = 1e-6 s`. The compiler recomputes the
`CurveValidationSummary` and refuses to trust an input summary; only
`validationPassed = true` may run live.

### Physical bounds are an optional typed context

This product decision fixes no concrete human speed/acceleration numbers, so none are
invented. `ContinuousCurveValidationContext` carries optional min/max speed, max
acceleration/deceleration and max speed gradient. Positivity/finiteness are always enforced;
when a context is supplied all bounds are checked (at breakpoints, including knots, using
`a = v · dv/dx`) and `physicalBoundsChecked = true`; otherwise mathematical validation still
runs and the flag is `false`. A production-eligibility bounds policy is a later pilot gate.

### 1.0 → 1.1 migration

`migrate_approved_pace_profile_1_0_to_1_1` is pure and non-mutating: each legacy leg becomes
a CONSTANT_SPEED segment (`speed = legDistance / legDuration`) plus a locked split; total
time, pool, start mode, stroke, workout goal, source authority, approval and coach-lock are
preserved; provenance records `migratedFromSchemaVersion`, `migrationVersion`,
`legacyProfileId/Version`. The legacy profile is **not** PCHIP-smoothed — its constant-leg
behaviour is preserved (leg boundaries bit-identical; mid-leg walls within the central
tolerance due to the resampling grid).

### Runtime integration (backward compatible)

`SessionAggregate`'s profile registry, `select_live_pace_profile` and the compiler accept
both schema versions (same authority/pool/start/stroke/distance checks; coach-lock
unchanged). The **GhostClock is not rewritten** — it keeps consuming a `PaceTimeline`;
StopPause freeze, temporary alignment, wall reconciliation, coach reset, active time and
official distance are unchanged. Official distance stays wall/geometry authoritative
(ADR-036); a wearable estimate never becomes official distance.

### Safe-wall coach continuous-curve reset

`CoachPacingReset` gains an optional `replacementPaceProfileRef`. Without it, existing coach
pacing-reset behaviour is unchanged. With it, the replacement profile is resolved,
authority/pool/stroke/start-mode-checked and compiled **at request time** (a failure rejects
the command atomically); the pending replacement is applied at the **next official wall** via
`GhostClock.apply_timeline_reset_at_wall`. This is **not** a StopPause: the active clock does
not freeze, `stoppedDuration` does not increase, prior splits/gap history are preserved, the
ghost keeps wall continuity (no mid-pool teleport), and future ghost movement comes from the
replacement timeline. Reset events carry optional previous/replacement profile refs; historical
replay adopts the replacement profile metadata after the applied event. Commit 7 persistence
is not rewritten.

### External data, features and reporting (contract only)

`NormalizedSwimmingRecord` gains optional continuous-curve fields (velocity, phase, turn,
stroke and curve-provenance columns) with missingness preserved and no fake filling;
`DataSourceRegistryEntry` gains optional capability flags. Split-only data may not be
presented as continuous ground truth; `swimcore` still cannot import `contracts.external_data`;
license/provenance requirements stand. Pure feature-extraction helpers live in
`swimtools.swimming_features` (IMU integration and load–velocity regression stay in the
research backlog). `ContinuousCurveReportContext` is added as an optional, forward-compatible
field on `PaceProfileReportContext` — Commit 8 computes none of it (that is Commit 9).

## ADR numbering

The continuous-curve decision is **ADR-038**, distinct from the existing **ADR-037** (event
journal & replay), which is kept and unchanged. ADR-034 is kept; its authority/approval/
source-priority/coach-lock decisions remain in force, and only its constant-leg execution is
extended/partially superseded here.

## Commands / Events / State

`CoachPacingReset.replacementPaceProfileRef` (optional). `CoachPacingResetRequested` /
`CoachPacingResetApplied` payloads gain optional previous/replacement profile refs +
replacement target total time. `PaceInterval` gains optional
`continuousPhaseIndex / curveSegmentIndex / curveRepresentation / curveProfileVersion`. New
generated schema `approved-pace-profile-1.1.json`; `approved-pace-profile-1.0.json` is
unchanged.

## Reversibility

1.1 is additive; 1.0 remains fully supported. The curve representation is enum-gated (PCHIP /
CONSTANT_SPEED), so a future representation is a new enum value + validator + compiler branch.
The planning ML architecture is a contract direction only — no model artifact is committed.

## Non-negotiables (also in CLAUDE.md)

Live runtime never runs planning ML or a PCHIP solver — it consumes a precompiled timeline.
PCHIP exists only in `swimcore.pacing`. The simulator never duplicates curve/pace/ghost/
clock/safety/replay logic. Zero/negative approved target velocity is forbidden. Locked split
durations are hard constraints and exact target-time reconciliation is mandatory (reject, not
clamp). A coach continuous-profile replacement applies only at a safe official wall and is not
a StopPause. Synthetic simulator data is never production performance evidence.

## Validation

`tests/unit/test_continuous_pace_contracts.py`, `test_pchip.py`,
`test_continuous_curve_reconciliation.py`, `test_continuous_pace_migration.py`,
`test_continuous_curve_session_integration.py`, `test_coach_continuous_curve_reset.py`,
`test_swimming_feature_extraction.py`, `test_external_data_continuous_fields.py`;
`tests/property/test_continuous_curve_invariants.py`,
`tests/property/test_simulator_determinism.py`; `tests/simulator/*`;
`tests/architecture/test_simulator_boundaries.py`. Demonstration A (two PCHIP curves, same
total + locked splits → equal wall times, different 12.5 m position) and Demonstration B
(legacy migration, timeline preserved, no smoothing) are covered.
