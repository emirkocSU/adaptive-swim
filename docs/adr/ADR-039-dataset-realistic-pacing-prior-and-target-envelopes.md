# ADR-039 — Dataset-Realistic Pacing Prior, Training Correction, Forecasting and Operational Target Envelopes

- **Status:** ACTIVE (Faz 1, Commit 8 — contracts, catalog, validators and planning docs only)
- **Date:** 2026-07-22
- **Related:** ADR-038 (continuous pace curves — runtime and compiler decision kept, scope
  clarified here), ADR-034 (approved pace profiles, coach authority), ADR-035 (planning ML
  vs live adaptation ML; coach authority), ADR-036 (official-distance authority), ADR-032
  (external data bootstrapping / provenance), ADR-031 (StopPause), ADR-037 (event journal
  and replay — unchanged)

## Context / Problem

Real datasets are now available: an official race pacing corpus, an IMU front-crawl sensor
corpus, a weekly-load and sprint-repeat training corpus, and a package of controlled
studies (plus one quarantined stroke file). ADR-038 fixed the runtime — a continuous target
speed curve compiled to an exact deterministic timeline — and named a **phase-aware
conditional transformer with a spline decoder** as the long-term model architecture.

The available data does not support that architecture yet, and pretending it does would be
a scientific misstatement:

> **Measured instantaneous velocity ≠ operational target velocity envelope.**

None of these datasets provides real start, underwater, breakout, turn or intra-stroke
micro-velocity ground truth across all distances. Official race segments are coarse split
times. The IMU corpus is sensor research on one stroke at one course length, without
official-distance authority. The controlled studies give processed statistics, not
continuous position-time truth.

## Decision

### 1. ADR-038 stands; its model-architecture wording is scoped

The continuous runtime, the compiler, exact reconciliation, the coach safe-wall curve
reset, the PCHIP-only representation and the deterministic ghost remain exactly as decided
in ADR-038. **ADR-038 is not deleted or superseded.** What is clarified: the phase-aware
conditional transformer is a *long-term architectural target*, to be reconsidered when
high-resolution continuous data exists. It must not be presented as the active architecture
of the first data-driven model.

### 2. The first active model is a coarse conditional split prior

The first data-driven planning model is:

```
coarse conditional race pacing prior
  + bounded training-domain residual correction
  + optional forecasting head
  + bounded operational target-envelope shape
  + exact total/locked-split reconciliation
```

It is a **sequence-level conditional split prior**, not a micro-phase model. It predicts a
split *distribution*, never a total time and never a measured velocity trace.

### 3. No fake phase labels

Datasets without genuine phase labels must never be given synthetic ones. The continuous
profile phase contract stays available for coach-authored profiles, templates, and truly
labelled data only.

### 4. Training correction is small and regularized

Domain correction from race distribution to training distribution is a **small regularized
residual**, expressed as
`p_train = softmax(log(p_race + eps) + delta_train)` — not a free re-fit. The correction is
bounded, its context completeness is recorded, and a missing training context is never
imputed.

### 5. Forecast is separate from target

`coachTargetTimeSec` (a target) and `predictedNextRepeatTimeSec` / `predictedNextSplitTimeSec`
(forecasts) are separate contract fields in separate models. A forecast NEVER mutates a
coach target. Under out-of-distribution or domain-extrapolation conditions,
`BOUNDED_AUTO` is forbidden — only `SUGGEST_ONLY` or the `SAFE_BASELINE` remain. Repeat
fatigue forecasting is a forecast, **not** a minimum-fatigue optimizer.

### 6. Operational envelope, not measured velocity

The generated within-length shape is a **bounded template** or a coarse learned latent
shape. It is labelled as such through the curve provenance (`curveOrigin`,
`curveEvidenceLevel`, `visualShapeSource`, `continuousCurveGroundTruth = false`) and is
never called `predictedMeasuredVelocity`. The correct names are *target velocity envelope* /
*operational ghost velocity curve*.

### 7. Exact reconciliation stays a hard constraint

Whatever a model proposes, the deterministic compiler still reconciles exactly to the
target total time and to every locked split, and still rejects (never clamps) a curve that
violates a supplied physical bound after reconciliation.

### 8. External data earns no production eligibility

Catalogued datasets are research assets. A license that is not `VERIFIED_ALLOWED` blocks
production training. A quarantined asset may only serve pipeline smoke tests and can never
enter a production model or a primary research analysis. `productionTrainingEligible=false`
cannot be overridden. Missing metadata is never fabricated.

### 9. Coach authority and deterministic runtime are unchanged

Nothing in this ADR touches the live loop. No model output reaches the ghost or the light
directly; every pace change still passes the deterministic SafetyController. The live loop
stays offline, deterministic and free of pandas/NumPy.

## Consequences

- Commit 8 adds **contracts, catalog, validators, leakage guards, feature utilities,
  planning documentation and evidence metadata only**. No `src/ml/`, no training run.
- Raw datasets stay outside the repository and outside the package; the catalog carries
  hashes and expectations.
- Phase 5A–5E (see `docs/plan/model-roadmap.md`) sequences the actual model work, and every
  learned model must beat the deterministic baselines before it may be considered.

## Alternatives considered

- **Train the phase-aware transformer now.** Rejected: the data cannot supervise
  within-length velocity; the result would be a confident fabrication.
- **Call the produced curve a predicted measured velocity.** Rejected: it is an operational
  target envelope; the naming is a safety and honesty issue, not a style preference.
- **One production-eligibility flag per file.** Rejected: the training corpus mixes license
  regimes per source/row; eligibility is gated per row/source.
