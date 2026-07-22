"""Curve evidence, forecast/target separation, finite contracts and analytic bound tests.

Commit 8 correction §2.6, §2.7, §2.8, §9, §12.
"""

from __future__ import annotations

import math

import pytest

from contracts.continuous_pace import (
    ContinuousPaceCurve,
    CurveProvenance,
    PaceCurveKnot,
    TargetTimeConstraint,
)
from contracts.enums import (
    ContinuousCurveGenerationMode,
    CurveEvidenceLevel,
    CurveOrigin,
    ForecastSuggestionMode,
    PaceCurveRepresentation,
    Stroke,
    TargetTimeSource,
    VisualShapeSource,
)
from contracts.forecasting import RepeatForecastContext, RepeatForecastOutput
from swimcore.pacing.continuous_curve import (
    ContinuousCurveValidationContext,
    build_evaluable_curve,
)
from swimcore.pacing.curve_bounds import ScaledRegion, check_curve_physical_bounds
from swimcore.pacing.profile_compiler import ProfileCompilationError


# --------------------------------------------------------------------------- §2.8 finite
@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
def test_infinity_and_nan_are_rejected_in_curve_knots(bad: float) -> None:
    with pytest.raises(ValueError):
        PaceCurveKnot(knotIndex=0, distanceM=0.0, targetSpeedMps=bad)
    with pytest.raises(ValueError):
        PaceCurveKnot(knotIndex=0, distanceM=bad, targetSpeedMps=1.2)


def test_positive_infinity_does_not_satisfy_a_positive_constraint() -> None:
    with pytest.raises(ValueError):
        TargetTimeConstraint(targetTotalTimeSec=math.inf, source=TargetTimeSource.COACH)


@pytest.mark.parametrize("bad", [math.inf, math.nan])
def test_infinity_rejected_in_tolerance_and_confidence(bad: float) -> None:
    with pytest.raises(ValueError):
        TargetTimeConstraint(
            targetTotalTimeSec=80.0, source=TargetTimeSource.COACH, toleranceSec=bad
        )
    with pytest.raises(ValueError):
        CurveProvenance(
            generationMode=ContinuousCurveGenerationMode.TEMPLATE,
            targetTimeSource=TargetTimeSource.TEMPLATE,
            curveConfidence=bad,
        )


# --------------------------------------------------------------------------- §9 provenance
def test_coarse_split_derived_curve_cannot_claim_ground_truth() -> None:
    with pytest.raises(ValueError, match="continuousCurveGroundTruth"):
        CurveProvenance(
            generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
            targetTimeSource=TargetTimeSource.COACH,
            curveEvidenceLevel=CurveEvidenceLevel.COARSE_SPLIT_DERIVED,
            continuousCurveGroundTruth=True,
        )


def test_bounded_template_shape_cannot_claim_ground_truth() -> None:
    with pytest.raises(ValueError, match="continuousCurveGroundTruth"):
        CurveProvenance(
            generationMode=ContinuousCurveGenerationMode.TEMPLATE,
            targetTimeSource=TargetTimeSource.TEMPLATE,
            visualShapeSource=VisualShapeSource.BOUNDED_TEMPLATE,
            continuousCurveGroundTruth=True,
        )


def test_dataset_evidence_provenance_round_trips() -> None:
    prov = CurveProvenance(
        generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
        targetTimeSource=TargetTimeSource.COACH,
        curveOrigin=CurveOrigin.RACE_PRIOR_TRAINING_CORRECTED,
        curveEvidenceLevel=CurveEvidenceLevel.COARSE_SPLIT_DERIVED,
        visualShapeSource=VisualShapeSource.BOUNDED_TEMPLATE,
        trainingDomainCorrectionApplied=True,
        trainingContextCompleteness=0.4,
        sourceDatasetAssetIds=("adaptive_swim_unified_official_pacing_all_sources_v3",),
        sourceDatasetManifestVersions=("1.0.0",),
    )
    assert prov.continuousCurveGroundTruth is False
    assert prov.sourceDatasetAssetIds is not None
    dumped = prov.model_dump(mode="json")
    assert dumped["curveOrigin"] == "RACE_PRIOR_TRAINING_CORRECTED"


def test_legacy_provenance_without_evidence_fields_still_parses() -> None:
    """Backward compatibility: existing 1.1 profile JSON has none of the new fields."""
    prov = CurveProvenance.model_validate(
        {"generationMode": "TEMPLATE", "targetTimeSource": "TEMPLATE"}
    )
    assert prov.curveOrigin is None
    assert prov.continuousCurveGroundTruth is False


def test_target_and_prediction_fields_stay_separate() -> None:
    prov = CurveProvenance(
        generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
        targetTimeSource=TargetTimeSource.COACH,
        targetSplitTimesSec=(40.0, 41.0),
        predictedSplitTimesSec=(39.2, 42.4),
    )
    assert prov.targetSplitTimesSec == (40.0, 41.0)
    assert prov.predictedSplitTimesSec == (39.2, 42.4)


# --------------------------------------------------------------------------- §12 forecast
def test_forecast_never_mutates_the_coach_target() -> None:
    context = RepeatForecastContext(
        athleteRef="a1",
        stroke=Stroke.freestyle,
        poolLengthM=25,
        repeatDistanceM=100.0,
        repeatIndex=3,
        completedRepeatTimesSec=(72.1, 73.0, 74.2),
        coachTargetTimeSec=72.0,
    )
    output = RepeatForecastOutput(
        coachTargetTimeSec=context.coachTargetTimeSec,
        predictedNextRepeatTimeSec=75.4,
        targetMissRisk=0.8,
        suggestionMode=ForecastSuggestionMode.SUGGEST_ONLY,
        modelVersion="baseline-last-repeat-1.0.0",
    )
    assert context.coachTargetTimeSec == 72.0
    assert output.coachTargetTimeSec == 72.0
    assert output.predictedNextRepeatTimeSec != output.coachTargetTimeSec


def test_bounded_auto_is_forbidden_when_out_of_distribution() -> None:
    with pytest.raises(ValueError, match="BOUNDED_AUTO"):
        RepeatForecastOutput(
            predictedNextRepeatTimeSec=75.0,
            suggestionMode=ForecastSuggestionMode.BOUNDED_AUTO,
            modelVersion="m1",
            oodFlag=True,
        )


def test_bounded_auto_is_forbidden_under_domain_extrapolation() -> None:
    with pytest.raises(ValueError, match="BOUNDED_AUTO"):
        RepeatForecastOutput(
            predictedNextRepeatTimeSec=75.0,
            suggestionMode=ForecastSuggestionMode.BOUNDED_AUTO,
            modelVersion="m1",
            domainExtrapolationFlag=True,
        )


def test_safe_baseline_is_allowed_out_of_distribution() -> None:
    output = RepeatForecastOutput(
        predictedNextRepeatTimeSec=75.0,
        suggestionMode=ForecastSuggestionMode.SAFE_BASELINE,
        modelVersion="m1",
        oodFlag=True,
    )
    assert output.suggestionMode is ForecastSuggestionMode.SAFE_BASELINE


def test_target_miss_risk_requires_a_target() -> None:
    with pytest.raises(ValueError, match="targetMissRisk"):
        RepeatForecastOutput(
            predictedNextRepeatTimeSec=75.0,
            targetMissRisk=0.5,
            suggestionMode=ForecastSuggestionMode.SUGGEST_ONLY,
            modelVersion="m1",
        )


# --------------------------------------------------------------------------- §2.7 analytic bounds
def _curve(knots: list[tuple[float, float]]) -> ContinuousPaceCurve:
    return ContinuousPaceCurve(
        representation=PaceCurveRepresentation.PCHIP,
        knots=tuple(
            PaceCurveKnot(knotIndex=i, distanceM=d, targetSpeedMps=s)
            for i, (d, s) in enumerate(knots)
        ),
    )


def test_analytic_check_accepts_a_calm_curve() -> None:
    evaluable = build_evaluable_curve(_curve([(0.0, 1.25), (50.0, 1.25), (100.0, 1.25)]))
    ctx = ContinuousCurveValidationContext(
        minimumSpeedMps=0.5,
        maximumSpeedMps=2.5,
        maximumAccelerationMps2=1.0,
        maximumDecelerationMps2=1.0,
        maximumSpeedGradientPerM=0.5,
    )
    check_curve_physical_bounds(evaluable, ctx)


def test_analytic_check_catches_a_violation_between_sampling_points() -> None:
    """A spike narrower than the 0.10 m grid must still be rejected (sampling is not proof)."""
    # knots 0.05 m apart create an interior extremum far above the endpoint values
    evaluable = build_evaluable_curve(
        _curve([(0.0, 1.20), (0.05, 2.60), (0.10, 1.20), (100.0, 1.25)])
    )
    ctx = ContinuousCurveValidationContext(maximumSpeedMps=2.0)
    with pytest.raises(ProfileCompilationError, match="speed maximum"):
        check_curve_physical_bounds(evaluable, ctx)


def test_analytic_gradient_bound_is_enforced() -> None:
    evaluable = build_evaluable_curve(_curve([(0.0, 1.0), (10.0, 2.0), (100.0, 1.2)]))
    ctx = ContinuousCurveValidationContext(maximumSpeedGradientPerM=0.01)
    with pytest.raises(ProfileCompilationError, match="dv/dd"):
        check_curve_physical_bounds(evaluable, ctx)


def test_analytic_acceleration_bound_is_enforced() -> None:
    evaluable = build_evaluable_curve(_curve([(0.0, 1.0), (5.0, 2.2), (100.0, 1.2)]))
    ctx = ContinuousCurveValidationContext(maximumAccelerationMps2=0.05)
    with pytest.raises(ProfileCompilationError, match="acceleration"):
        check_curve_physical_bounds(evaluable, ctx)


def test_scaled_region_reproduces_post_reconciliation_speeds() -> None:
    """A pace scale factor of 2 halves the speed, which can breach a minimum-speed bound."""
    evaluable = build_evaluable_curve(_curve([(0.0, 1.20), (100.0, 1.20)]))
    ctx = ContinuousCurveValidationContext(minimumSpeedMps=1.0)
    check_curve_physical_bounds(evaluable, ctx)  # unscaled passes
    with pytest.raises(ProfileCompilationError, match="speed minimum"):
        check_curve_physical_bounds(
            evaluable,
            ctx,
            regions=(ScaledRegion(0.0, 100.0, 2.0),),
            stage="post-reconciliation",
        )


def test_no_bounds_supplied_is_a_no_op() -> None:
    evaluable = build_evaluable_curve(_curve([(0.0, 1.25), (100.0, 1.25)]))
    check_curve_physical_bounds(evaluable, ContinuousCurveValidationContext())
