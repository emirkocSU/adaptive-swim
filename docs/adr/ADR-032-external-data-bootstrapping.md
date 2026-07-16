# ADR-032 — External Data Bootstrapping Strategy

- **Status:** NEW (Phase 1: document + plan-level contract draft only)
- **Date:** 2026-07-16

## Context / Problem

Real Adaptive Swim training data does not exist yet. External data can bootstrap
simulator realism, cold-start priors, and non-production baselines — but must never be
mistaken for, or blended into, the final production adaptive model. A strict role
taxonomy prevents leakage and false performance claims.

## Decision

Five-layer taxonomy with hard role boundaries; none equals the final production model.

| Layer | Role | Hard boundary |
|---|---|---|
| L1 — Race Pacing Prior | Natural pacing curves by distance/stroke, split-index effect, simulator realism, cold-start prior | Not training data; behavioural response to ghost, coach-target adherence, adaptation effect cannot be learned from it |
| L2 — Wearable Sensor Pretraining | swim/rest split, turn/transition detection, lap segmentation, sensor-quality scoring, stop-like suggestion, split reliability | Not a substitute for the final pacing model |
| L3 — User-Consented Training Exports | Real training length/lap datasets, stroke count/rate, pace, rest, SWOLF, HR trends, next-length baselines, pre-pilot feature pipeline | Explicit consent + provenance + purpose required |
| L4 — Simulator Synthetic | Controller edge cases, replay, abstain, bad/delayed split, StopPause, ghost alignment, sensor dropout, failure injection | Not sporting-performance evidence; never claims production accuracy; never merged with real data by hiding source; always `synthetic=true` + scenario provenance |
| L5 — Adaptive Swim Proprietary | **Primary source for the final production adaptive model** | Final claims only via athlete-grouped + time-aware validation on this data |

## Commands / Events / State

None in Phase 1. This ADR governs data contracts and process only.

## Analytics / ML consequences

The v1.1 ML Activation Gate (G1–G7) is preserved unchanged. Pre-gate research
(source research, license/access verification, parser prototypes, cleaning, schema
mapping, pacing-prior analysis, simulator calibration, non-production baselines,
wearable task-specific research) may NOT connect to the edge runtime, may NOT control
`bounded_auto`, may NOT be packaged as a production artifact, and may NOT form a product
performance claim. Production ML activation happens only after G1–G7.

Confidence: `confidence = quantile interval width` is forbidden (v1.1 ADR-030). Quantile
is only one input to the uncertainty system.

## Reversibility

HIGH for the plan-level contracts (draft only). The import boundary
(`swimcore` ↛ `contracts.external_data`) is enforced by import-linter.

## Validation tests

`data_domain` required before any merge; no production-eligibility flag on external
records; synthetic records must carry `synthetic=true` + provenance; ambiguous
license/access → `TBD_VERIFICATION_REQUIRED`.
