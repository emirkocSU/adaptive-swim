# Model roadmap — Phase 5A–5E (ADR-039)

No model is trained in Commit 8. This document sequences the work that *may* start once
Phase 1 is closed. `src/ml/` does not exist yet and must not be created before Phase 5.

## Ground rules

- The first active model is a **coarse conditional split prior**, not a micro-phase model.
- Every learned model must be compared against the deterministic baselines below; a model
  that does not beat them does not ship.
- Whatever the model proposes, the deterministic compiler still reconciles **exactly** to
  the target total time and to every locked split, and still rejects a curve that violates
  a supplied physical bound (never clamps).
- Partitions follow the leakage rules in `docs/data/data-leakage-and-partitioning.md`;
  athlete-grouped and time-aware splits are mandatory where the dataset requires them.
- Forecast outputs never mutate a coach target. Under OOD or domain extrapolation,
  `BOUNDED_AUTO` is forbidden.

## Baselines (must be implemented and reported before any learned model)

| Baseline | Applies to |
|---|---|
| Even split | split-ratio prediction |
| Event median split ratio | split-ratio prediction |
| Stroke × distance × pool median | split-ratio prediction |
| Nearest performance-band prior | split-ratio prediction |
| Last repeat | repeat-time forecasting |
| Moving average | repeat-time forecasting |
| EWMA / linear trend | repeat-time forecasting |
| Gradient-boosted split-ratio model | split-ratio prediction |

A conditional transformer may only be evaluated **against** this table, never instead of it.

## Phase 5A — Coarse conditional race split prior

- Source: `adaptive_swim_unified_official_pacing_all_sources_v3` (role `RACE_PACING_PRIOR`).
- Target: the split-ratio vector conditioned on stroke, distance, pool length, start mode,
  sex/age band and performance band. **Never** a total time, never a velocity trace.
- Partitioning: `race_uid` in one partition; athlete held-out evaluation supported; random
  row splits forbidden; relay legs never collapsed into individual results.
- Gate: production training stays blocked while `source_license_status` is not
  `VERIFIED_ALLOWED`. Phase 5A therefore runs as *research* until licenses are verified.

## Phase 5B — Regularized training-domain residual correction

- Source: `adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1` (role
  `TRAINING_DOMAIN_CORRECTION`), with `ATHLETE_WEEK` and `SPRINT_REPEAT` kept as separate
  target tables, plus the controlled studies as a fatigue-shape prior.
- Method: `p_train = softmax(log(p_race + eps) + delta_train)` with a bounded `delta`.
- Constraint: the correction is small and regularized; a missing training context is
  recorded as missing (`trainingContextCompleteness`), never imputed.

## Phase 5C — Forecasting heads

Separate heads, separate outputs, all recorded through `RepeatForecastOutput`:

- next split time,
- remaining time,
- next repeat time,
- pace fade,
- quantiles (P10 / P50 / P90).

A forecast is advisory. It is not an optimizer, and specifically not a "minimum fatigue"
optimizer.

## Phase 5D — Constrained operational target-envelope compiler

Turns a coarse split distribution into a bounded within-length envelope:

- bounded template or coarse learned latent shape only;
- provenance stamped (`curveOrigin`, `curveEvidenceLevel`, `visualShapeSource`,
  `continuousCurveGroundTruth = false`);
- exact reconciliation to the target total and locked splits;
- full physical-bound verification (analytic, post-reconciliation).

## Phase 5E — FORM export and pilot athlete calibration

- Personalisation from a consented wearable export (e.g. FORM Smart Swim 2) and pilot
  sessions; personal calibration weight grows with personal data volume.
- `curveEvidenceLevel` may then reach `TRAINING_EXPORT_PERSONALIZED` or
  `PILOT_PERSONALIZED`; only genuinely continuous, verified position-time data could ever
  justify `continuousCurveGroundTruth = true`.

## When `src/ml/` opens

At Phase 5 start, and with this structure:

```
src/ml/
  data/            loaders over validated bundles (never raw, unvalidated files)
  features/        pure feature builders reusing swimtools.swimming_features
  baselines/       the table above
  race_prior/      Phase 5A
  training_correction/  Phase 5B
  forecasting/     Phase 5C
  curve/           Phase 5D envelope compiler adapter
  personalization/ Phase 5E
  evaluation/      leakage-checked evaluation harness
```

Until then the runtime carries **no** pandas/NumPy dependency and `swimcore` reads no
dataset at all.
