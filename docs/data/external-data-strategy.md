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
