# Dataset model roles (real-bundle catalog)

The authoritative machine-checked records are `data/catalog/*.json`. Raw ZIP/CSV files are
not committed.

| Bundle/member | Role | License/eligibility | Production training |
|---|---|---|---|
| Official race bundle | `RACE_PACING_PRIOR` | `TBD_VERIFICATION_REQUIRED` → `LICENSE_BLOCKED` | no |
| IMU bundle | `SENSOR_ENCODER_RESEARCH`, `TECHNIQUE_FEATURE_RESEARCH` | reported CC0, unverified; research eligible | no |
| Training/fatigue bundle | `TRAINING_DOMAIN_CORRECTION`, `REPEAT_FATIGUE_PRIOR` | mixed by source; research eligible | no |
| External controlled-study segment member | fatigue/technique/personal-calibration research | reported CC0, unverified; research eligible | no |
| External controlled-study long member | sensor-feature/auditable research | reported CC0, unverified; research eligible | no |
| External massage member | advisory/recovery research, **condition-aware only** | reported CC BY 4.0, unverified; research eligible | no |
| External quarantined stroke member | `PIPELINE_SMOKE_TEST_ONLY` | blocked; `SMOKE_TEST_ONLY` | **never** |

## Structural facts verified from the supplied bundles

- Official race: 128,475 rows × 151 columns; `continuous_curve_ground_truth=False` for all
  rows; source licenses remain TBD.
- IMU: 40,957 rows × 94 columns; `official_distance_authority=NOT_OFFICIAL_DISTANCE`.
- Training/fatigue: 396 rows × 111 columns; real discriminator is
  `record_granularity`, with 228 `ATHLETE_WEEK` and 168 `SPRINT_REPEAT` rows.
- External studies is **one seven-member ZIP**. Its four data members contain 232 controlled
  segments, 18,082 long measurements, 1,767 massage rows and 2,010 quarantined stroke rows.
  The stroke member reports `production_training_eligible=False`,
  `research_primary_analysis_eligible=False` and `pipeline_smoke_test_eligible=True` on every
  row.

## Claims that remain forbidden

- None of these bundles is measured instantaneous-velocity ground truth.
- IMU is not official distance and not the primary pacing target.
- A source-level or row-level license marked TBD is not production eligible.
- Massage cannot be collapsed into generic fatigue data without `condition_label`.
- The quarantined stroke member cannot enter production or primary research.

The generated product object remains an **operational target velocity envelope** learned
from race/research/training distributions and corrections, reconciled exactly to target time
and splits.

## Reporting boundary

Dataset roles describe how a target profile may have been produced. They do not authorize a
session metric. Commit 9 copies approved profile evidence metadata into report provenance but
never infers a dataset role, changes license eligibility, reads quarantined files or treats a
coarse target envelope as measured continuous velocity.


## Phase 1 closure boundary (ADR-041)

The Phase 1 vertical slice carries dataset evidence **only** as approved-profile provenance
(`curveOrigin`, `curveEvidenceLevel`, `visualShapeSource`, `continuousCurveGroundTruth`,
`sourceDatasetAssetIds`). The `dataset-evidence-provenance` e2e case proves that such a
profile runs in the deterministic runtime, that the report carries the asset ids, that it is
never presented as measured velocity ground truth, that no raw dataset is read and that
runtime never alters license eligibility.

**Data catalog / model evidence ≠ session performance evidence.**
