# ADR-036 — Start mode and official-distance authority

- **Status:** ACTIVE (Faz 1)
- **Date:** 2026-07-18
- **Supersedes / Superseded by:** compatible with ADR-031 (StopPause & ghost alignment)

## Context / Problem

Workout 1.1 makes start mode and pool length mandatory execution context, and the newest
product decision requires that a dive / strong push-off must not jump the ghost forward and
that a wearable's mid-pool distance estimate must never rewrite official distance.

## Decision

`StartMode` (`DIVE_START`, `IN_WATER_PUSH_START`, `IN_WATER_STATIC_START`) is resolved
deterministically: repeat override → block start mode → workout `StartPolicy.defaultMode`.
The resolved start mode is never ambiguous.

**Official distance authority** comes only from:
`WORKOUT_GEOMETRY`, `WALL_VERIFICATION`, `COMPLETED_LENGTH_COUNT`, `EXTERNAL_VERIFIED_WALL`.

A wearable/IMU `estimatedDistanceM`:
- never changes official distance on a normal start,
- never jumps the ghost forward,
- never interprets `DIVE_START` as beginning at 5 m,
- never records a 50 m length as 45 m,
- never creates an official split,
- may only be a temporary *visual* alignment input during a confirmed StopPause.

For `DIVE_START` the official distance at start is always 0 m. The start/underwater leg may
be analyzed as 0–15 m, but it is never subtracted from the completed distance.

## State changes

Session official-distance accounting must not read `SwimmerState.estimatedDistanceM`. Only
the StopPause path may accept a tracked alignment, and that alignment stays visual.

## Reversibility

The rule set is additive; legacy 1.0 sessions (no start mode) are unaffected because they
never enter the profile path.

## Validation tests

`test_official_distance_authority`, `test_start_mode_resolution`, and the wearable-safety
assertions in the session tests.
