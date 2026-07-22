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

## Commit 7 invariants (append-only journal + replay, ADR-037)

- I-C7-1   One command's events are exactly one `EventBatchRecord` and one canonical JSONL
           line; a torn final line removes the whole command batch (no half command).
- I-C7-2   The canonical codec is byte-deterministic (UTF-8, no BOM, `sort_keys`, compact,
           one `\n`); NaN/Infinity are rejected on encode and decode.
- I-C7-3   `append_batch` reports success only after write **and** fsync complete; on file
           creation the parent directory is synced too.
- I-C7-4   Resending the exact same batch never writes a second line
           (`ALREADY_PRESENT`); a same-seq/command-id/overlap difference is a conflict.
- I-C7-5   After an fsync failure the fully-written line is recognised on retry; the line
           is never auto-deleted, and a later batch can still append.
- I-C7-6   A torn final line is truncated only in repair mode (`LogTailTruncated`, exact
           byte counts); bytes before the last complete newline are never touched.
- I-C7-7   A valid-but-unterminated final record is retained; repair appends only `\n`
           (`MissingFinalNewlineRepaired`), which is not data loss.
- I-C7-8   Middle corruption, a newline-terminated invalid final line, and blank lines are
           `CorruptEventLogError`; corruption is never skipped.
- I-C7-9   Replay executes no commands, never rewinds runtime clocks, and uses no
           time/randomness/uuid/filesystem; identical events → identical state.
- I-C7-10  `elapsed = active + stopped` and `wall = elapsed + lifecyclePaused` always hold
           and are all non-negative; a violation raises `ReplayDurationError`.
- I-C7-11  The retroactive StopPause start is the payload `startedAtMs`, never the
           confirmation event timestamp; StopPause never changes the lifecycle state.
- I-C7-12  Replayed official distance is a pool-length multiple from geometry; a wearable
           source never rewrites it.
- I-C7-13  Golden journals are byte-deterministic — committed bytes equal the regenerated
           bytes and are sha256-equal across directories.
- I-C7-14  `SessionRecovered` is never auto-produced or auto-appended; on replay it changes
           no lifecycle state and only increments `recoveryCount`.

## Commit 8 invariants (continuous pace curves + simulator, ADR-038)

- I-C8-1   A leg/split/total duration is a time constraint; within-length pace comes from the
           approved curve.
- I-C8-2   Approved curve knot speeds are strictly positive and finite; zero/negative is
           rejected.
- I-C8-3   Compilation is deterministic and bit-identical for the same profile.
- I-C8-4   The integrated total equals the target within `CURVE_TIME_TOLERANCE_SEC`; each
           locked split equals its target within the same tolerance.
- I-C8-5   Reconciliation rejects (never clamps) on negative remainder, non-finite/non-positive
           speed, or a post-reconciliation physical-bound violation.
- I-C8-6   The `CurveValidationSummary` is recomputed by the compiler; only `validationPassed`
           runs live.
- I-C8-7   Two different curves with the same total and same locked splits yield equal wall
           times but may differ mid-length (Demonstration A).
- I-C8-8   1.0→1.1 migration preserves the timeline (leg boundaries bit-identical), never
           smooths, and never mutates the input (Demonstration B).
- I-C8-9   Both profile versions are selectable/compilable; the GhostClock is unchanged.
- I-C8-10  A coach continuous-curve reset applies only at a safe official wall, adds no stopped
           duration, freezes no clock, and preserves prior splits (not a StopPause).
- I-C8-11  Official distance stays wall/geometry authoritative; a wearable estimate never
           rewrites it.
- I-C8-12  The PCHIP implementation is defined exactly once, in `swimcore.pacing`.
- I-C8-13  The simulator redefines no core type and duplicates no curve/pace/ghost/clock/
           safety/replay logic; it embeds the real runtime.
- I-C8-14  A scenario produces byte-identical journals across runs; provenance marks
           `usedRealHumanData=False` and `SYNTHETIC_SIMULATION`.
- I-C8-15  Live runtime never runs planning ML or a PCHIP solve; it consumes a precompiled
           timeline.


## Commit 8 correction invariants (ADR-039)

1. The eight required scenario slugs exist and none aliases a demo scenario.
2. Same scenario + same seed → identical observation trace, event stream and journal
   SHA-256; a different seed changes the trace while every domain invariant still holds.
3. Each virtual-swimmer tick is exactly `tickMs` apart; wall crossings are interpolated
   inside the crossing tick and are never snapped to the tick grid.
4. `normal-pace-loss` produces a gap that grows and persists while the ghost is still
   running, with no StopPause and zero stopped duration.
5. A duplicate `MarkStopPause` (same clientCommandId, same content) produces zero new events
   and zero new journal batches; exactly one open interval results.
6. A rejected `CompleteSession` during an open StopPause changes neither the aggregate, the
   event sequence nor the journal.
7. Planned rest never creates a StopPause and never increases stopped duration.
8. Low position confidence never changes official distance or the completed length count.
9. A safe-wall coach reset adopts the full replacement metadata in live state and in replay,
   is not a StopPause, and preserves past split history.
10. `physicalBoundsChecked = true` implies the reconciled timeline passed every supplied
    bound at its reconciled scale, verified analytically.
11. `+inf`, `-inf` and `NaN` never enter a continuous contract field.
12. A dataset manifest with a non-`VERIFIED_ALLOWED` license can never be production
    eligible, and a quarantined asset can only serve `PIPELINE_SMOKE_TEST`.
13. No catalogued dataset may be used as a measured continuous-velocity target.
14. A grouping key (race, athlete, trial, pre/post, crossover unit, time series) never spans
    two partitions, and a forecast label never enters the feature allowlist.

## Commit 9 report invariants (ADR-040)

1. Same inputs produce the same report model, bytes, ID and SHA-256.
2. Event sequence permutation/duplication is rejected by historical replay validation.
3. Supplied replay state must equal a fresh fold of the supplied canonical events.
4. `wall = elapsed + lifecyclePaused`; `elapsed = active + stopped`.
5. Official completed distance is wall-count × pool length only.
6. Eligible split count never exceeds official split count.
7. Excluded splits remain visible but never affect aggregates.
8. Missing target/observation/sensor values remain `None`, never fabricated zero.
9. Continuous metrics require finite, monotonic, trusted, in-bounds observations.
10. StopPause, planned rest, lifecycle pause and coach reset remain separate.
11. Safe-wall replacement metadata applies only from its effective length onward.
12. Target and forecast fields remain separate.
13. Synthetic provenance is never dropped.
14. Canonical JSON roundtrip is stable and finite-only.
15. Report schema version is fixed to the concrete 1.1 contract and cannot disagree with provenance.
16. Any change to effective report content or its workout/profile/timeline/registry/observation/
    sensor/policy input digests changes `reportId`.
17. Every coach-reset replacement profile and compiled timeline referenced by replay is supplied
    explicitly; the initial profile is never used as a fallback.
18. Workout, profile, timeline and replay-selected profile identities and geometry are coherent.
19. Trusted curve observations lie inside the session horizon; velocity-only observations require
    the session start or a trusted position anchor.
20. Wall reconciliation is counted only after a later official wall event; pending is separate.
21. Planned-rest observations are excluded from the non-rest quality-ratio denominator.
22. Report persistence accepts canonical bytes only.
23. Absent positive/negative split extrema remain `None`, never synthetic zero.


## Phase 1 closure invariants (ADR-041)

1. Journal event sequence starts at 1, is contiguous and has no duplicates; event ids are
   unique; timestamps never decrease; batch bounds are correct; journal line count equals the
   persisted batch count.
2. Live aggregate state and historical replay agree on lifecycle, official distance, split
   count, all selected-profile metadata and all timing axes.
3. `elapsed = active + stopped` and `wall = elapsed + lifecyclePaused`; stopped equals the sum
   of completed StopPause intervals; a pace loss or a coach curve reset creates no stopped
   time.
4. Official distance equals completed length count × pool length, never exceeds the planned
   distance, lands only on verified walls, and is never produced by an estimate.
5. Approved profile, workout and compiled timeline agree on pool, stroke, start mode and
   distance; the reconciled timeline meets the target total; locked splits are preserved.
6. Report session id, last sequence, event digest, content-addressed id and canonical bytes
   all match the journal it was derived from; provenance matches the final replay state.
7. Target fields and forecast fields stay separate; unavailable metrics stay `None`.
8. A rejected command persists no event and leaves no sequence gap; a duplicate retry adds no
   journal line.
9. The same case and seed produce identical journal, report and manifest bytes; the output
   directory never changes them.
10. Migration preserves the compiled target function: totals and endpoints exactly, sampled
    targets and report split targets within `MIGRATION_TARGET_TOLERANCE_SEC`.
11. Every emitted artifact is canonical UTF-8 JSON/JSONL with LF endings and contains no
    absolute path, timestamp, UUID, environment value or raw dataset reference.
12. Synthetic simulator output is always marked synthetic and is never performance evidence.

## Phase 1 closure test bindings (mechanically checked)

The following twenty bindings are the release-closure index consumed by
`python -m swimtools.completeness_check`. Each target must remain a real pytest function.

- I-P1-01 -> tests/e2e/test_cross_component_invariants.py::test_event_invariants
- I-P1-02 -> tests/e2e/test_cross_component_invariants.py::test_live_and_replay_state_agree
- I-P1-03 -> tests/e2e/test_cross_component_invariants.py::test_clock_axes_stay_separate
- I-P1-04 -> tests/e2e/test_cross_component_invariants.py::test_official_distance_invariants
- I-P1-05 -> tests/e2e/test_phase1_vertical_slice.py::test_slice_completes_and_passes_every_invariant
- I-P1-06 -> tests/e2e/test_phase1_vertical_slice.py::test_journal_is_the_authoritative_input_of_the_report
- I-P1-07 -> tests/e2e/test_cross_component_invariants.py::test_target_and_forecast_stay_separate
- I-P1-08 -> tests/e2e/test_failure_atomicity.py::test_a_rejected_command_appends_nothing
- I-P1-09 -> tests/e2e/test_e2e_determinism.py::test_same_case_same_seed_is_byte_identical
- I-P1-10 -> tests/e2e/test_phase1_case_matrix.py::test_case_three_migration_equivalence
- I-P1-11 -> tests/e2e/test_phase1_vertical_slice.py::test_bundle_contains_exactly_the_canonical_members
- I-P1-12 -> tests/e2e/test_cross_component_invariants.py::test_dataset_evidence_is_not_performance_evidence
- I-P1-13 -> tests/unit/test_session_atomicity.py::test_failed_command_preserves_runtime_reference_graph
- I-P1-14 -> tests/e2e/test_e2e_determinism.py::test_run_id_covers_profiles_replacement_and_analytics_policy
- I-P1-15 -> tests/e2e/test_e2e_bundle_verifier.py::test_recomputed_run_id_is_required
- I-P1-16 -> tests/e2e/test_e2e_bundle_verifier.py::test_manifest_binds_outcomes_and_observations
- I-P1-17 -> tests/e2e/test_phase1_case_matrix.py::test_legacy_case_executes_a_real_workout_1_0_source
- I-P1-18 -> tests/architecture/test_phase1_completeness.py::test_repository_is_mechanically_complete
- I-P1-19 -> tests/e2e/test_backward_compatibility_matrix.py::test_workout_1_0_still_parses_and_migrates
- I-P1-20 -> tests/architecture/test_e2e_boundaries.py::test_e2e_layer_order_is_respected
