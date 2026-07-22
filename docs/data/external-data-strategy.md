# External Data Strategy (applicable guide to ADR-032)

Five layers with hard role boundaries: L1 Race Pacing Prior, L2 Wearable Sensor
Pretraining, L3 User-Consented Training Exports, L4 Simulator Synthetic, L5 Adaptive Swim
Proprietary (the only source for final production claims).

- Pre-gate research is separate from production ML activation and may never touch the edge
  runtime, control `bounded_auto`, ship as a production artifact, or make a performance
  claim.
- The v1.1 ML Activation Gate (G1–G7) is preserved.
- `contracts.external_data` is plan-level only and must never be imported by `swimcore`
  (import-linter forbidden rule).
- Merging race / training / adaptive-swim records without `data_domain` is forbidden.
- No external dataset can earn production eligibility on its own.

## Planning-model provenance (mainline, §15)

`DataSourceRegistryEntry` now carries explicit planning-model provenance: `sourceUrl`,
`license`, `licenseVerified`, `retrievedAt`, `transformationVersion`, `dataQualityLevel`,
`allowedUsage`. A source is planning-model eligible only when its license is explicitly
verified and not left as `TBD_VERIFICATION_REQUIRED`. `NormalizedSwimmingRecord` gains
optional planning features (total/split times, split ratio, start mode, turn count, reaction
time, 15 m/final-section times, HR zone/recovery, stroke rate/count, distance-per-stroke,
percent-of-personal-best, biomechanical/physiological feature maps). All new fields are
optional — missingness is preserved and never fake-filled — and the synthetic-data and
no-production-eligibility rules are unchanged. The first planning model is trained on
licensed open data and must pass the Planning Model Gate P1–P7 (ADR-035) before live use.


## Update (ADR-039, Commit 8 correction)

Concrete datasets are now catalogued in `data/catalog/` — see
`docs/data/dataset-model-roles.md` for the role table and
`docs/data/data-leakage-and-partitioning.md` for the partitioning rules. Key points:

- Raw bundles are operator-provided and gitignored (`data/external/raw/`); only manifests
  and expectations are checked in.
- A license that is not `VERIFIED_ALLOWED` blocks production training. The official race
  pacing corpus is therefore research-only until per-source verification completes.
- The quarantined stroke dataset may only serve pipeline smoke tests.
- No catalogued dataset is an official-distance authority, and none is continuous-velocity
  ground truth.

## Real-bundle header correction (Commit 8 corrected v2)

The four supplied bundles were opened and their exact filenames/headers were inspected.
Raw validation now uses source names, including `source_participant_id`,
`session_or_trial_id` and `record_granularity`. Canonical names are produced only by the
mapping in `raw-to-canonical-mapping.md`.

The external-studies ZIP is one bundle with controlled-study, massage, quarantine, manifest,
QA and README members. The quarantined stroke CSV is not a separate ZIP and cannot cause the
other expected members to be reported as unexpected. File-level policy keeps it
`SMOKE_TEST_ONLY`, while controlled studies remain research eligible and massage remains
condition-aware advisory/recovery research.
