# DELTA MANIFEST — Phase 1 through Commit 8 corrected v2

## Section A — pre-Commit 7 mainline delta

## ADDED (38):
IMPLEMENTATION_REPORT.md
docs/adr/ADR-034-distance-specific-approved-pace-profiles.md
docs/adr/ADR-035-pre-session-planning-ml-and-coach-authority.md
docs/adr/ADR-036-start-mode-and-official-distance-authority.md
src/contracts/examples/semantic_invalid_v1_1/repeat_override_index_invalid.json
src/contracts/examples/valid_v1_1/100m_sprint_positive_split.json
src/contracts/examples/valid_v1_1/200_free_race_v1_1.json
src/contracts/examples/valid_v1_1/200m_25m_coach_authored.json
src/contracts/examples/valid_v1_1/200m_25m_dive_133s_model_approved.json
src/contracts/examples/valid_v1_1/200m_25m_inwater_133s_model_approved.json
src/contracts/examples/valid_v1_1/800m_negative_split_profile.json
src/contracts/pace_profiles.py
src/contracts/physiology.py
src/contracts/schemas/approved-pace-profile-1.0.json
src/contracts/schemas/workout-1.1.json
src/swimcore/ghost/__init__.py
src/swimcore/ghost/errors.py
src/swimcore/pacing/profile_compiler.py
src/swimcore/pacing/profile_selection.py
src/swimcore/time/__init__.py
src/swimcore/time/errors.py
src/swimcore/time/sim_clock.py
src/swimcore/workout/start_mode.py
tests/property/test_profile_and_session_invariants.py
tests/unit/_profile_helpers.py
tests/unit/test_approved_pace_profile_contracts.py
tests/unit/test_external_data_planning_contracts.py
tests/unit/test_official_distance_authority.py
tests/unit/test_pace_profile_compiler.py
tests/unit/test_pace_profile_selection.py
tests/unit/test_safety_profile_authority.py
tests/unit/test_session_atomicity.py
tests/unit/test_session_commit6_completeness.py
tests/unit/test_session_current_profile_context.py
tests/unit/test_session_split_identity.py
tests/unit/test_start_mode_resolution.py
tests/unit/test_workout_v1_1_migration.py
tests/unit/test_workout_v1_1_schema.py

## CHANGED (35):
ARCHITECTURE.md
CLAUDE.md
README.md
docs/adr/README.md
docs/data/external-data-strategy.md
docs/domain/glossary.md
docs/plan/phase1-commit-plan.md
docs/testing/invariants.md
docs/testing/test-strategy.md
pyproject.toml
src/contracts/analytics.py
src/contracts/commands.py
src/contracts/enums.py
src/contracts/events.py
src/contracts/external_data.py
src/contracts/schemas/event-envelope-1.0.json
src/contracts/schemas/session-report-1.0.json
src/contracts/schemas/workout-1.0.json
src/contracts/workout.py
src/swimcore/control/safety.py
src/swimcore/control/types.py
src/swimcore/pacing/__init__.py
src/swimcore/pacing/curves.py
src/swimcore/pacing/timeline.py
src/swimcore/pacing/types.py
src/swimcore/session/__init__.py
src/swimcore/session/aggregate.py
src/swimcore/workout/__init__.py
src/swimcore/workout/context.py
src/swimcore/workout/migrations.py
src/swimcore/workout/rules.py
src/swimcore/workout/validator.py
src/swimtools/arch_check.py
src/swimtools/gen_schemas.py
tests/unit/test_safety_controller.py

## REMOVED from original (3):
src/contracts/examples/invalid/gap_in_segments.json
src/contracts/examples/invalid/target_faster_than_fastest_allowed.json
src/contracts/examples/invalid/target_slower_than_slowest_allowed.json


## Section B — Commit 8 acceptance correction + dataset evidence plan (ADR-039)

### ADDED
```
data/README.md
data/catalog/adaptive_swim_external_studies_5_6_7_model_ready_v1.json
data/catalog/adaptive_swim_sensor_imu_frontcrawl_model_ready_v1.json
data/catalog/adaptive_swim_stroke_dataset_quarantined_v1.json
data/catalog/adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1.json
data/catalog/adaptive_swim_unified_official_pacing_all_sources_v3.json
data/external/raw/.gitignore
data/schemas/controlled_studies.json
data/schemas/imu_sensor.json
data/schemas/quarantine.json
data/schemas/race_pacing_segments.json
data/schemas/training_fatigue.json
docs/adr/ADR-039-dataset-realistic-pacing-prior-and-target-envelopes.md
docs/data/data-leakage-and-partitioning.md
docs/data/dataset-model-roles.md
docs/plan/model-roadmap.md
src/contracts/data_assets.py
src/contracts/forecasting.py
src/swimcore/pacing/curve_bounds.py
src/swimtools/data_catalog.py
src/swimtools/data_splitting.py
src/swimtools/validate_dataset_bundle.py
tests/architecture/test_dataset_boundaries.py
tests/unit/test_curve_evidence_and_bounds.py
tests/unit/test_data_leakage_guards.py
tests/unit/test_dataset_catalog.py
tests/unit/test_feature_helpers_adr039.py
tests/unit/test_post_reconciliation_bounds.py
tests/simulator/goldens/coach-continuous-curve-reset.jsonl
tests/simulator/goldens/long-stop-mid-length.jsonl
tests/simulator/goldens/normal-pace-loss.jsonl
```

### CHANGED
```
.importlinter                                   (contracts 6–8: dataset/forecast, pandas/numpy, simulator)
ARCHITECTURE.md                                 (dataset evidence layer; analytic bound verification)
CLAUDE.md                                       (non-negotiables 36–48; dependency + forbidden lists)
DELTA_MANIFEST.md                               (this file)
IMPLEMENTATION_REPORT.md                        (retitled; Commit 8 correction section)
README.md                                       (Commit 8 scope, dataset validation, status)
docs/adr/README.md                              (ADR-039 row; ADR-038 scope note)
docs/adr/ADR-038-continuous-pace-curves-and-phase-aware-model-generation.md (scope clarification)
docs/data/data-source-registry.md               (registered assets)
docs/data/external-data-strategy.md             (ADR-039 update)
docs/data/normalized-research-schema.md         (data/schemas pointer)
docs/data/synthetic-data-rules.md               (run manifest / synthetic never evidence)
docs/domain/event-catalog.md                    (reset + created payload additions)
docs/domain/glossary.md                         (ADR-039 vocabulary)
docs/domain/state-machines.md                   (scenario ↔ state-rule table)
docs/plan/deferred-map.md                       (ADR-039 deferrals)
docs/plan/first-10-commits.md                   (status pointer)
docs/plan/phase1-commit-plan.md                 (single authoritative status table; correction section)
docs/testing/invariants.md                      (14 correction invariants)
docs/testing/phase1-completeness.md             (CI scope; operator-only dataset validation)
docs/testing/test-strategy.md                   (new suites)
src/contracts/_base.py                          (finite constrained types)
src/contracts/continuous_pace.py                (finite fields; ADR-039 provenance + validator)
src/contracts/enums.py                          (curve evidence, dataset, forecast enums)
src/contracts/events.py                         (optional reset/created metadata)
src/contracts/schemas/approved-pace-profile-1.1.json   (regenerated)
src/contracts/schemas/event-batch-record-1.0.json      (regenerated)
src/contracts/schemas/event-envelope-1.0.json          (regenerated)
src/simulator/__init__.py                       (new exports)
src/simulator/cli.py                            (seed, manifest output)
src/simulator/harness.py                        (rewritten: injections, result, internal replay check)
src/simulator/provenance.py                     (run manifest, deterministic runId)
src/simulator/scenarios.py                      (eight required scenarios; demos retained)
src/simulator/virtual_swimmer.py                (tick-based simulation)
src/swimcore/pacing/__init__.py                 (pace/speed distance queries)
src/swimcore/pacing/continuous_profile_compiler.py (scaled regions; analytic pre/post bounds)
src/swimcore/pacing/timeline.py                 (target_pace_at_distance / target_speed_at_distance)
src/swimcore/replay/reducer.py                  (full replacement metadata adoption)
src/swimcore/replay/state.py                    (profile timeline metadata fields)
src/swimcore/session/aggregate.py               (profile metadata capture + full swap)
src/swimcore/session/types.py                   (PendingCoachReset replacement metadata)
src/swimtools/run_scenario.py                   (real seed; aliases removed; richer report)
src/swimtools/swimming_features.py              (six ADR-039 helpers)
tests/property/test_simulator_determinism.py    (defaultSeed; explicit-seed determinism)
tests/replay/goldens/*.jsonl                    (regenerated for the additive payload fields)
tests/simulator/test_scenarios.py               (rewritten for the eight scenarios)
tests/simulator/test_virtual_swimmer.py         (rewritten for the tick model + CLI)
```

### REMOVED
```
tests/simulator/goldens/coach-curve-reset-session.jsonl
tests/simulator/goldens/long-stop-continuous-session.jsonl
tests/simulator/goldens/normal-continuous-session.jsonl
```
(replaced by goldens named after the required scenario slugs)

### NOT ADDED (deliberately)
```
src/ml/                    — opens in Phase 5 (ADR-039 §10)
data/external/raw/*.zip    — raw bundles stay operator-local and gitignored
pandas / numpy / scipy     — never a runtime dependency
```


## Section C — Commit 8 corrected v2: real raw bundle compatibility

This section is the delta from `adaptive-swim-commit8-corrected-full.zip` to
`adaptive-swim-commit8-corrected-full-v2.zip`. It contains no raw dataset ZIP or CSV.

### ADDED (1)
```text
docs/data/raw-to-canonical-mapping.md
```

### CHANGED (23)
```text
DELTA_MANIFEST.md
IMPLEMENTATION_REPORT.md
README.md
data/README.md
data/catalog/adaptive_swim_external_studies_5_6_7_model_ready_v1.json
data/catalog/adaptive_swim_sensor_imu_frontcrawl_model_ready_v1.json
data/catalog/adaptive_swim_stroke_dataset_quarantined_v1.json
data/catalog/adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1.json
data/catalog/adaptive_swim_unified_official_pacing_all_sources_v3.json
data/schemas/controlled_studies.json
data/schemas/imu_sensor.json
data/schemas/quarantine.json
data/schemas/race_pacing_segments.json
data/schemas/training_fatigue.json
docs/data/data-leakage-and-partitioning.md
docs/data/data-source-registry.md
docs/data/dataset-model-roles.md
docs/data/external-data-strategy.md
docs/data/normalized-research-schema.md
src/contracts/data_assets.py
src/swimtools/data_catalog.py
src/swimtools/validate_dataset_bundle.py
tests/unit/test_dataset_catalog.py
```

### REMOVED (0)

None.

### CORRECTION SUMMARY

- Replaced invented raw requirements with the exact supplied CSV headers.
- Added explicit raw-to-canonical mappings for `subject_uid`, `session_uid` and
  `record_type`; canonical names are no longer required in raw files.
- Counted `ATHLETE_WEEK` and `SPRINT_REPEAT` from the real `record_granularity` column.
- Modeled external studies as one seven-member ZIP and the quarantined stroke CSV as a
  file-level `SMOKE_TEST_ONLY` asset with `validationPrimary=false`.
- Recorded exact supplied bundle/member SHA-256 values, row/column counts and allowed raw
  values.
- Kept license-TBD data production-ineligible, IMU non-authoritative for distance and all
  coarse datasets non-ground-truth for measured instantaneous velocity.
- Added representative tests for raw headers, normalization, multi-file external bundles,
  file-level quarantine, granularity counts, license gating, hash mismatch and missing raw
  columns.
- Confirmed by byte comparison that `swimcore`, simulator, persistence, replay fixtures and
  simulator fixtures are unchanged from the supplied corrected full repository.
- Synchronized README and implementation report final status to `READY_FOR_COMMIT_9`.
