# Invariants (bound to tests as they are implemented)

Contract-level invariants proven in Commit 2:

- I-C2-1  JSON Schema uses only standard draft 2020-12 keywords.
- I-C2-2  Pace vocabulary is locked; banned names appear nowhere.
- I-C2-3  Generated schemas equal the committed schemas (`make schema-check`).
- I-C2-4  Valid golden workouts pass schema; schema-invalid examples are rejected.
- I-C2-5  No general `IncidentStarted` / `IncidentResolved` event names; StopPause terms used.
- I-C2-6  `activeDurationSec` / `stoppedDurationSec` / `elapsedDurationSec` present on
          length/report contracts.
- I-C2-7  `performanceRelatedStopProbability` is optional/advisory on the efficiency contract.
- I-C2-8  External records require `data_domain` to merge; no production-eligibility flag;
          synthetic records carry `synthetic=true` + provenance.

Behavioural invariants (StopPause, safety controller, replay, simulator) are added with
their commits (3–10).

## Mainline invariants (approved pace profiles)

- I-M-1  Approved-profile leg durations sum exactly to `targetTotalTimeSec` (tol 1e-6); the
         core never silently normalizes.
- I-M-2  A profile's compiled timeline duration equals its `targetTotalTimeSec`.
- I-M-3  Profile selection is deterministic and returns the highest-authority eligible
         candidate; an equal-priority tie raises rather than picking silently.
- I-M-4  A DRAFT/REJECTED profile can never start a session.
- I-M-5  A coach-locked profile never receives ML/rule auto-apply (`COACH_PROFILE_LOCKED`).
- I-M-6  Official completed distance is always a pool-length multiple and never exceeds the
         workout total; wearable estimates never rewrite it.
- I-M-7  Profile legs are not official wall splits.
- I-M-8  Resolved start mode is never ambiguous (repeat → block → default).
- I-M-9  ML request with missing confidence or data quality abstains
         (`ML_CONFIDENCE_MISSING` / `DATA_QUALITY_MISSING`), never APPLY.
