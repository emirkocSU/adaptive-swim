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
