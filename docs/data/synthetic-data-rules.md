# Synthetic Data Rules

- Every synthetic record carries `synthetic=true` plus scenario/seed provenance.
- Synthetic data is **not** sporting-performance evidence and is never used in a
  production-accuracy claim.
- Synthetic and real records are never merged by hiding the source; `data_domain` and
  provenance are always preserved.
- Missingness is preserved; no fake filling.


## Update (ADR-039, Commit 8 correction)

Simulator output is stamped with a `SimulationRunManifest` whose `synthetic` flag is always
`true` and whose `runId` is a pure hash of the run identity (no timestamp, no UUID).
Synthetic athlete traces are never external-dataset training evidence and never production
performance evidence, and simulation provenance is never mixed with dataset evidence
provenance: a scenario profile may carry ADR-039 curve provenance (origin, evidence level,
visual shape source) while the run itself stays `SYNTHETIC_SIMULATION` with
`usedRealHumanData = false` and `licenseVerified = false`.
