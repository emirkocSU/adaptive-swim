"""Continuous compiler: reconciliation, compilation and inverse-query tests (§36)."""

from __future__ import annotations

import pytest

from contracts.continuous_pace import SplitTimeConstraint
from swimcore.pacing.continuous_curve import ContinuousCurveValidationContext
from swimcore.pacing.continuous_profile_compiler import (
    CURVE_TIME_TOLERANCE_SEC,
    compile_continuous_pace_profile,
)
from swimcore.pacing.profile_compiler import ProfileCompilationError
from swimcore.pacing.timeline import (
    ghost_distance_at_active_time,
    target_active_time_at_distance,
)
from tests.unit._continuous_helpers import knots, pchip_profile

TOL = CURVE_TIME_TOLERANCE_SEC


def _compile(profile, **kw):  # noqa: ANN001, ANN003
    return compile_continuous_pace_profile(
        profile,
        pool_length_m=kw.get("pool", profile.poolLengthM),
        resolved_start_mode=profile.startMode,
        stroke=profile.stroke,
        total_distance_m=kw.get("total", profile.totalDistanceM),
        validation_context=kw.get("ctx"),
    )


def test_total_integral_within_tolerance() -> None:
    p = pchip_profile(curve_knots=knots((0.0, 1.30), (50.0, 1.15), (100.0, 1.32)), target_time=80.0)
    plan = _compile(p)
    assert abs(plan.validationSummary.integratedTotalTimeSec - 80.0) <= TOL
    assert plan.validationSummary.totalReconciliationErrorSec <= TOL
    assert plan.validationSummary.validationPassed


def test_locked_split_integral_exact() -> None:
    p = pchip_profile(
        curve_knots=knots((0.0, 1.30), (50.0, 1.10), (100.0, 1.35)),
        target_time=80.0,
        locked_splits=(
            SplitTimeConstraint(
                splitIndex=0, fromM=0.0, toM=50.0, targetDurationSec=42.0, lockedByCoach=True
            ),
        ),
    )
    plan = _compile(p)
    t50 = target_active_time_at_distance(plan.timeline, 50.0).elapsedActiveSec
    assert abs(t50 - 42.0) <= TOL
    assert abs(plan.timeline.totalActiveDurationSec - 80.0) <= TOL


def test_two_internal_curves_same_total_and_splits() -> None:
    # Equal wall times are guaranteed only when the splits are locked; the two curves then
    # differ in mid-length shape but share every wall time (Demonstration A).
    locked = tuple(
        SplitTimeConstraint(
            splitIndex=i,
            fromM=i * 25.0,
            toM=(i + 1) * 25.0,
            targetDurationSec=20.0,
            lockedByCoach=True,
        )
        for i in range(4)
    )
    a = pchip_profile(
        curve_knots=knots((0.0, 1.5), (50.0, 1.1), (100.0, 1.3)), locked_splits=locked
    )
    b = pchip_profile(
        curve_knots=knots((0.0, 1.1), (50.0, 1.5), (100.0, 1.2)), locked_splits=locked
    )
    pa = _compile(a)
    pb = _compile(b)
    assert abs(pa.timeline.totalActiveDurationSec - pb.timeline.totalActiveDurationSec) <= TOL
    # same wall targets (locked to 20 s each)
    for i, wall in enumerate((25.0, 50.0, 75.0, 100.0), start=1):
        ta = target_active_time_at_distance(pa.timeline, wall).elapsedActiveSec
        tb = target_active_time_at_distance(pb.timeline, wall).elapsedActiveSec
        assert abs(ta - tb) < 1e-3
        assert abs(ta - i * 20.0) < 1e-3
    # but the mid-length 12.5 m position differs
    ma = target_active_time_at_distance(pa.timeline, 12.5).elapsedActiveSec
    mb = target_active_time_at_distance(pb.timeline, 12.5).elapsedActiveSec
    assert abs(ma - mb) > 0.1


def test_distance_time_roundtrip() -> None:
    p = pchip_profile(curve_knots=knots((0.0, 1.30), (50.0, 1.12), (100.0, 1.34)))
    plan = _compile(p)
    for d in (10.0, 25.0, 37.5, 62.5, 90.0):
        t = target_active_time_at_distance(plan.timeline, d).elapsedActiveSec
        back = ghost_distance_at_active_time(plan.timeline, t).distanceM
        assert abs(back - d) < 1e-3


def test_time_distance_roundtrip() -> None:
    p = pchip_profile(curve_knots=knots((0.0, 1.30), (50.0, 1.12), (100.0, 1.34)))
    plan = _compile(p)
    total = plan.timeline.totalActiveDurationSec
    for frac in (0.1, 0.25, 0.5, 0.75, 0.9):
        t = total * frac
        d = ghost_distance_at_active_time(plan.timeline, t).distanceM
        back = target_active_time_at_distance(plan.timeline, d).elapsedActiveSec
        assert abs(back - t) < 1e-3


def test_bit_identical_interval_compilation() -> None:
    p = pchip_profile(curve_knots=knots((0.0, 1.3), (50.0, 1.15), (100.0, 1.35)))
    a = _compile(p)
    b = _compile(p)
    assert a.timeline == b.timeline


def test_compiled_speeds_positive_and_finite() -> None:
    plan = _compile(pchip_profile(curve_knots=knots((0.0, 1.5), (50.0, 1.1), (100.0, 1.4))))
    assert plan.validationSummary.minTargetSpeedMps > 0.0


def test_negative_remaining_time_rejected() -> None:
    # lock the first 50 m to more than the whole target -> rejected at contract level
    with pytest.raises(Exception):  # noqa: B017,PT011 - contract or compiler rejection
        pchip_profile(
            target_time=80.0,
            locked_splits=(
                SplitTimeConstraint(
                    splitIndex=0, fromM=0.0, toM=50.0, targetDurationSec=85.0, lockedByCoach=True
                ),
            ),
        )


def test_physical_bounds_rejects_out_of_range() -> None:
    p = pchip_profile(curve_knots=knots((0.0, 1.30), (50.0, 1.10), (100.0, 1.35)))
    ctx = ContinuousCurveValidationContext(minimumSpeedMps=1.20, maximumSpeedMps=1.40)
    with pytest.raises(ProfileCompilationError):
        _compile(p, ctx=ctx)


def test_physical_bounds_checked_flag() -> None:
    p = pchip_profile(curve_knots=knots((0.0, 1.25), (100.0, 1.25)))
    plan_no_ctx = _compile(p)
    assert plan_no_ctx.validationSummary.physicalBoundsChecked is False
    ctx = ContinuousCurveValidationContext(minimumSpeedMps=1.0, maximumSpeedMps=2.0)
    plan_ctx = _compile(p, ctx=ctx)
    assert plan_ctx.validationSummary.physicalBoundsChecked is True


def test_pool_context_mismatch_rejected() -> None:
    p = pchip_profile(pool=25)
    with pytest.raises(ProfileCompilationError, match="pool"):
        _compile(p, pool=50)


def test_summary_is_compiler_authoritative() -> None:
    p = pchip_profile(curve_knots=knots((0.0, 1.3), (50.0, 1.1), (100.0, 1.4)))
    plan = _compile(p)
    s = plan.validationSummary
    assert s.compiledIntervalCount == len(plan.timeline.intervals)
    assert s.knotCount == 3
    assert s.phaseCount == 1
    assert s.compilerVersion.startswith("continuous-")


def test_post_reconciliation_bound_violation_rejected() -> None:
    """Reconciliation scales speeds; a bound satisfied pre-scale but broken post-scale rejects."""
    # curve speeds ~1.25; target 80s keeps ~1.25. Lock 0-50 to a very fast 30s -> speeds ~1.6
    # there, exceeding a 1.45 max after scaling.
    p = pchip_profile(
        curve_knots=knots((0.0, 1.25), (50.0, 1.25), (100.0, 1.25)),
        target_time=80.0,
        locked_splits=(
            SplitTimeConstraint(
                splitIndex=0, fromM=0.0, toM=50.0, targetDurationSec=30.0, lockedByCoach=True
            ),
        ),
    )
    ctx = ContinuousCurveValidationContext(minimumSpeedMps=1.0, maximumSpeedMps=1.45)
    with pytest.raises(ProfileCompilationError):
        _compile(p, ctx=ctx)
