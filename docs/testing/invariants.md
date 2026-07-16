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
