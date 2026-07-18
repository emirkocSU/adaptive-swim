# ADR-035 — Pre-session planning ML and coach authority

- **Status:** ACTIVE (Faz 1: contract + gate definition only)
- **Date:** 2026-07-18
- **Supersedes / Superseded by:** complements ADR-028 (ML Activation Gate) for the live path

## Context / Problem

There are now two distinct ML roles and they must never be conflated:

1. **Pre-session Pace Planning Model** — proposes a profile type, distributes a target total
   time into leg/split ratios, estimates physiological risk/confidence, and offers the coach
   alternatives. It does *not* run in the live loop and can be trained on licensed open data
   before any personal data exists.
2. **Live Adaptation ML** — proposes the next safe-boundary pace during a session, always
   behind the deterministic `SafetyController`, governed by the existing G1–G7 gate.

## Decision

- The planning model output is born as a **DRAFT** profile and cannot enter a live session
  without coach approval or an explicit default policy.
- A **Planning Model Gate P1–P7** must pass before a planning model may be used as a live
  plan source:
  - **P1** license and allowed-use verified
  - **P2** provenance complete
  - **P3** pool/start/stroke/distance coverage adequate
  - **P4** athlete-grouped, source-aware validation complete
  - **P5** split ratios sum exactly and target-time reconciliation passes
  - **P6** confidence/calibration and OOD policy defined
  - **P7** coach review/approval path and deterministic export tested
- If the gate does not pass, the product remains fully functional on manual profiles,
  templates, and deterministic legacy segments.
- Personalization roadmap:
  `Final approved profile = general model prediction + personal calibration + coach constraints`.
  Coach feedback is never treated as automatic ground truth; it is stored with quality and
  context. Versioned metadata: `generalModelVersion`, `personalCalibrationVersion`,
  `coachConstraintVersion`, `profileGenerationId`.

## Non-negotiables

- ML plans; the deterministic core executes approved plans.
- ML never controls the ghost, the clock, or StopPause directly.
- A coach-authored / coach-locked profile has the highest authority; ML cannot auto-override
  it (`COACH_PROFILE_LOCKED`).
- Missing confidence or data quality on an ML request → abstain, fall back to the coach plan
  (`ML_CONFIDENCE_MISSING` / `DATA_QUALITY_MISSING`).

## Reversibility

Both models are optional. Removing them leaves a complete manual/template product.

## Validation tests

`test_safety_profile_authority`, `test_safety_controller`, and the external-data planning
contract tests (`test_external_data_planning_contracts`).
