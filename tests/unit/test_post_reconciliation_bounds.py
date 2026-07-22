"""Post-reconciliation physical-bound enforcement in the compiler (Commit 8 §2.6)."""

from __future__ import annotations

import pytest

from contracts.continuous_pace import (
    ApprovedContinuousPaceProfile,
    ContinuousPaceCurve,
    ContinuousPacePhase,
    CurveProvenance,
    PaceCurveKnot,
    SplitTimeConstraint,
    TargetTimeConstraint,
)
from contracts.enums import (
    ContinuousCurveGenerationMode,
    ContinuousPacePhaseType,
    PaceCurveRepresentation,
    PaceProfileSource,
    PaceProfileType,
    ProfileApprovalStatus,
    StartMode,
    Stroke,
    TargetTimeSource,
    WorkoutGoal,
)
from swimcore.pacing.continuous_curve import ContinuousCurveValidationContext
from swimcore.pacing.continuous_profile_compiler import compile_continuous_pace_profile
from swimcore.pacing.profile_compiler import ProfileCompilationError


def _profile(
    *,
    target_time: float,
    knots: list[tuple[float, float]],
    splits: tuple[SplitTimeConstraint, ...] = (),
    total: float = 100.0,
) -> ApprovedContinuousPaceProfile:
    return ApprovedContinuousPaceProfile(
        profileId="bounds",
        profileVersion="1",
        source=PaceProfileSource.COACH_AUTHORED,
        profileType=PaceProfileType.EVEN_PACE,
        approvalStatus=ProfileApprovalStatus.COACH_APPROVED,
        poolLengthM=25,
        startMode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        workoutGoal=WorkoutGoal.RACE_PACE,
        totalDistanceM=total,
        targetTimeConstraint=TargetTimeConstraint(
            targetTotalTimeSec=target_time, source=TargetTimeSource.COACH
        ),
        splitTimeConstraints=splits,
        curve=ContinuousPaceCurve(
            representation=PaceCurveRepresentation.PCHIP,
            knots=tuple(
                PaceCurveKnot(knotIndex=i, distanceM=d, targetSpeedMps=s)
                for i, (d, s) in enumerate(knots)
            ),
        ),
        phases=(
            ContinuousPacePhase(
                phaseIndex=0,
                fromM=0.0,
                toM=total,
                phaseType=ContinuousPacePhaseType.SURFACE_SWIM,
            ),
        ),
        curveProvenance=CurveProvenance(
            generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
            targetTimeSource=TargetTimeSource.COACH,
        ),
    )


def _compile(profile: ApprovedContinuousPaceProfile, ctx: ContinuousCurveValidationContext):  # noqa: ANN202
    return compile_continuous_pace_profile(
        profile,
        pool_length_m=25,
        resolved_start_mode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        total_distance_m=profile.totalDistanceM,
        validation_context=ctx,
    )


def test_bounds_checked_flag_only_set_after_the_post_check_passes() -> None:
    profile = _profile(target_time=80.0, knots=[(0.0, 1.25), (100.0, 1.25)])
    ctx = ContinuousCurveValidationContext(
        minimumSpeedMps=0.5,
        maximumSpeedMps=2.5,
        maximumAccelerationMps2=1.0,
        maximumDecelerationMps2=1.0,
        maximumSpeedGradientPerM=0.5,
    )
    plan = _compile(profile, ctx)
    assert plan.validationSummary.physicalBoundsChecked is True
    assert plan.validationSummary.validationPassed is True


def test_reconciliation_that_breaches_a_minimum_speed_is_rejected() -> None:
    """Scaling the curve to a much slower total must fail the post-reconciliation check."""
    profile = _profile(target_time=160.0, knots=[(0.0, 1.25), (100.0, 1.25)])
    ctx = ContinuousCurveValidationContext(minimumSpeedMps=1.0)
    with pytest.raises(ProfileCompilationError):
        _compile(profile, ctx)


def test_reconciliation_that_breaches_a_maximum_speed_is_rejected() -> None:
    profile = _profile(target_time=40.0, knots=[(0.0, 1.25), (100.0, 1.25)])
    ctx = ContinuousCurveValidationContext(maximumSpeedMps=2.0)
    with pytest.raises(ProfileCompilationError):
        _compile(profile, ctx)


def test_post_reconciliation_gradient_bound_is_enforced() -> None:
    """A gradient that is legal before scaling can breach its bound after scaling."""
    knots = [(0.0, 1.20), (50.0, 1.35), (100.0, 1.20)]
    # raw curve peaks at |dv/dd| ≈ 0.006 /m; scaling 3× faster triples it to ≈ 0.018 /m
    ctx_loose = ContinuousCurveValidationContext(maximumSpeedGradientPerM=0.008)
    # unscaled (target equals the integrated time) passes
    baseline = _compile(_profile(target_time=80.0, knots=knots), ctx_loose)
    integrated = baseline.validationSummary.integratedTotalTimeSec
    # a much faster target scales speeds up and the gradient with them → must be rejected
    faster = _profile(target_time=integrated / 3.0, knots=knots)
    with pytest.raises(ProfileCompilationError):
        _compile(faster, ctx_loose)


def test_post_reconciliation_acceleration_bound_is_enforced() -> None:
    knots = [(0.0, 1.10), (50.0, 1.45), (100.0, 1.10)]
    # acceleration scales with 1/f²: a 4× faster target multiplies |a| by 16
    ctx = ContinuousCurveValidationContext(maximumAccelerationMps2=0.05)
    baseline_profile = _profile(target_time=80.0, knots=knots)
    baseline = compile_continuous_pace_profile(
        baseline_profile,
        pool_length_m=25,
        resolved_start_mode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        total_distance_m=100.0,
        validation_context=ContinuousCurveValidationContext(),
    )
    integrated = baseline.validationSummary.integratedTotalTimeSec
    faster = _profile(target_time=integrated / 4.0, knots=knots)
    with pytest.raises(ProfileCompilationError):
        _compile(faster, ctx)


def test_locked_split_region_is_checked_with_its_own_scale() -> None:
    """Each reconciled region is verified at ITS scale, not at one global factor."""
    knots = [(0.0, 1.25), (50.0, 1.25), (100.0, 1.25)]
    splits = (
        SplitTimeConstraint(
            splitIndex=0, fromM=0.0, toM=50.0, targetDurationSec=20.0, lockedByCoach=True
        ),
    )
    profile = _profile(target_time=80.0, knots=knots, splits=splits)
    # first 50 m must run at 2.5 m/s (20 s), the rest at ~0.83 m/s (60 s)
    with pytest.raises(ProfileCompilationError):
        _compile(profile, ContinuousCurveValidationContext(maximumSpeedMps=2.0))
    with pytest.raises(ProfileCompilationError):
        _compile(profile, ContinuousCurveValidationContext(minimumSpeedMps=1.0))
    # a context that accommodates both regions compiles
    plan = _compile(
        profile,
        ContinuousCurveValidationContext(minimumSpeedMps=0.5, maximumSpeedMps=3.0),
    )
    assert plan.validationSummary.physicalBoundsChecked is True


def test_no_validation_context_records_bounds_unchecked() -> None:
    profile = _profile(target_time=80.0, knots=[(0.0, 1.25), (100.0, 1.25)])
    plan = compile_continuous_pace_profile(
        profile,
        pool_length_m=25,
        resolved_start_mode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        total_distance_m=100.0,
    )
    assert plan.validationSummary.physicalBoundsChecked is False
    assert plan.validationSummary.validationPassed is True
