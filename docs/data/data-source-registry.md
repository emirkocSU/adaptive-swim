# Data source registry

Every external source is registered before use. No access, commercial-use or redistribution
right is assumed. Ambiguous license/access remains `TBD_VERIFICATION_REQUIRED`.

The machine-readable registry is `data/catalog/*.json`. It records bundle/member hashes,
real raw shapes, required raw headers, normalized mappings, roles, file-level eligibility,
license state, restrictions and leakage rules.

## Registered primary bundles

1. `adaptive_swim_unified_official_pacing_all_sources_v3.zip`
2. `adaptive_swim_sensor_imu_frontcrawl_model_ready_v1.zip`
3. `adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1.zip`
4. `adaptive_swim_external_studies_5_6_7_model_ready_v1.zip`

`adaptive_swim_stroke_dataset_quarantined_v1` is a **file-level catalog alias** for the CSV
inside bundle 4. It has `validationPrimary=false`, so CLI `--bundle`/`--all` validates that ZIP
once through the seven-member primary manifest. Its smoke-test policy remains independently
queryable through `assert_file_view_allowed`.

Unknown metadata stays unknown. Normalization never grants license or production rights.
