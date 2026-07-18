# ADR-034 — Distance-specific approved pace profiles

- **Status:** ACTIVE (Faz 1)
- **Date:** 2026-07-18
- **Supersedes / Superseded by:** extends the legacy `PaceSegment` model; does not replace it

## Context / Problem

The legacy Workout 1.0 pace model is a per-block `PaceSegment` list. It cannot express a
distance-specific race profile whose leg durations are authored (or model-generated) and
then coach-approved, and it cannot distinguish a *profile leg* (an analytical phase such as
0–15 m start/underwater) from an *official wall split* (verified at a 25 m / 50 m wall).

The newest product decision (Adaptive_Swim_Model_Tabanli_Tempo_ve_Baslangic_Guncellemesi)
requires the deterministic core to *execute* an already-approved distance-specific profile,
without ever generating one at runtime.

## Decision

Introduce `ApprovedPaceProfile` as the single authoritative live plan input:

- Legs (`PaceProfileLeg`) cover the distance with no gap/overlap; the first leg starts at
  0 m; the last leg ends at the profile total distance.
- Leg `targetDurationSec` values sum *exactly* to `targetTotalTimeSec`
  (tolerance `FLOAT_TOLERANCE`); the core never silently normalizes.
- A profile carries `source`, `profileType`, `approvalStatus`, `coachLocked`, `poolLengthM`,
  `startMode`, `stroke`, `workoutGoal`, provenance metadata, and an optional advisory
  `PhysiologyTarget`.
- **Profile legs are not official wall splits.** Official distance comes only from verified
  wall boundaries (ADR-036).

Selection authority (highest first): `COACH_AUTHORED` > `COACH_APPROVED_MODEL` >
`DEFAULT_MODEL_GENERATED`. Default-model profiles require an explicit opt-in policy.
`TEMPLATE` and `LEGACY_SEGMENTS` sit below. A coach-locked winner blocks any automatic
ML/rule override. An unresolved tie raises `AmbiguousPaceProfileSelectionError` — never a
silent pick.

The deterministic compiler (`compile_approved_pace_profile`) expands each leg at a constant
leg pace and produces a bit-identical `PaceTimeline`. The same target total time with a
different start mode is allowed to yield a different leg distribution; the core executes the
approved distribution, it does not produce it.

## Commands / Events

`CreateSession` may reference a `paceProfileRef`. `SessionCreated` carries the selected
profile id/version/source/type and `profileCoachLocked`. Pace-profile lifecycle events
(`PaceProfileGenerated/Edited/Approved/Rejected/Selected/Locked`) are defined now for
forward-compatible persistence; authoring UI/ML lands in a later phase.

## Reversibility

Legacy 1.0 segment compilation stays fully functional. A product with no approved profiles
runs on templates / manual profiles / legacy segments.

## Validation tests

`test_approved_pace_profile_contracts`, `test_pace_profile_selection`,
`test_pace_profile_compiler`, and the property invariants under
`tests/property/test_profile_and_session_invariants`.
