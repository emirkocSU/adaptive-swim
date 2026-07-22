"""Deterministic compiler for approved continuous pace profiles (ADR-038).

Compiles an :class:`ApprovedContinuousPaceProfile` into the existing
:class:`~swimcore.pacing.types.PaceTimeline` so the existing GhostClock, analytic
duration math and time<->distance inverse are reused unchanged (no second ghost / time
engine, no second PCHIP implementation).

Pipeline:
    validate curve -> deterministic breakpoints -> evaluate target speeds -> speed->pace ->
    piecewise-linear PaceIntervals -> exact total-time + locked-split reconciliation ->
    PaceTimeline + authoritative CurveValidationSummary.

The compiled result is bit-identical for the same profile. The summary is recomputed by the
compiler (never trusted from the input); a live-eligible timeline requires
``validationPassed = True``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from contracts.continuous_pace import (
    ApprovedContinuousPaceProfile,
    CurveValidationSummary,
)
from contracts.enums import (
    PaceCurveRepresentation,
    PaceProfileSource,
    PaceProfileType,
    StartMode,
    Stroke,
)
from swimcore.pacing.continuous_curve import (
    ContinuousCurveValidationContext,
    EvaluableCurve,
    build_evaluable_curve,
)
from swimcore.pacing.curve_bounds import ScaledRegion, check_curve_physical_bounds
from swimcore.pacing.errors import InvalidPaceCurveError
from swimcore.pacing.profile_compiler import ProfileCompilationError
from swimcore.pacing.types import PaceInterval, PaceTimeline

#: Maximum sampling step (m) for the continuous-curve breakpoint grid. A single central
#: constant (ADR-038). 0.10 m keeps the inverse-query error far below the 1e-6 s tolerance
#: for realistic pool speeds while keeping interval counts tractable.
CONTINUOUS_CURVE_MAX_STEP_M: float = 0.10

#: Central time tolerance for exact reconciliation (ADR-038).
CURVE_TIME_TOLERANCE_SEC: float = 1e-6

#: Compiler version stamped into the validation summary (bump on math changes).
CONTINUOUS_COMPILER_VERSION: str = "continuous-1.1.0"

_GEOM_TOL = 1e-6


@dataclass(frozen=True, slots=True)
class CompiledContinuousPacePlan:
    """Frozen result of compiling a continuous profile."""

    timeline: PaceTimeline
    validationSummary: CurveValidationSummary
    profileId: str
    profileVersion: str
    profileSource: PaceProfileSource
    profileType: PaceProfileType


def _finite(v: float) -> bool:
    return not (math.isnan(v) or math.isinf(v))


def _phase_index_at(profile: ApprovedContinuousPaceProfile, mid_m: float) -> int:
    for phase in profile.phases:
        if phase.fromM - _GEOM_TOL <= mid_m <= phase.toM + _GEOM_TOL:
            return phase.phaseIndex
    return profile.phases[-1].phaseIndex


def _segment_index_at(
    curve_repr: PaceCurveRepresentation, evaluable: EvaluableCurve, mid_m: float
) -> int | None:
    if curve_repr is not PaceCurveRepresentation.CONSTANT_SPEED:
        return None
    for i, (from_m, to_m, _speed) in enumerate(evaluable._segments):  # noqa: SLF001
        if from_m - _GEOM_TOL <= mid_m <= to_m + _GEOM_TOL:
            return i
    return len(evaluable._segments) - 1  # noqa: SLF001


def _deterministic_breakpoints(
    profile: ApprovedContinuousPaceProfile,
    evaluable: EvaluableCurve,
    total: float,
) -> tuple[float, ...]:
    """Sorted, unique breakpoints: knots + phase + locked-split + wall boundaries + grid."""
    points: set[float] = {0.0, total}
    for d in evaluable.knot_distances:
        points.add(min(max(d, 0.0), total))
    for phase in profile.phases:
        points.add(phase.fromM)
        points.add(phase.toM)
    for split in profile.splitTimeConstraints:
        points.add(split.fromM)
        points.add(split.toM)
    pool = profile.poolLengthM
    walls = int(round(total / pool))
    for k in range(walls + 1):
        points.add(min(float(k * pool), total))
    # uniform max-step grid bounds the piecewise-linear pace interpolation error for both
    # PCHIP and constant-speed curves.
    n_steps = max(1, math.ceil(total / CONTINUOUS_CURVE_MAX_STEP_M))
    for i in range(n_steps + 1):
        points.add(min(total * i / n_steps, total))
    # dedupe within tolerance, keep sorted
    ordered = sorted(points)
    unique: list[float] = [ordered[0]]
    for p in ordered[1:]:
        if p - unique[-1] > _GEOM_TOL:
            unique.append(p)
    if abs(unique[-1] - total) > _GEOM_TOL:
        unique.append(total)
    return tuple(unique)


def _speed_to_pace(speed_mps: float) -> float:
    """sec/100m from m/s (smaller = faster)."""
    return 100.0 / speed_mps


def _raw_intervals(
    profile: ApprovedContinuousPaceProfile,
    evaluable: EvaluableCurve,
    breakpoints: tuple[float, ...],
    resolved_start_mode: StartMode,
) -> list[PaceInterval]:
    intervals: list[PaceInterval] = []
    for i in range(len(breakpoints) - 1):
        from_m = breakpoints[i]
        to_m = breakpoints[i + 1]
        length = to_m - from_m
        if length <= _GEOM_TOL:
            continue
        mid = (from_m + to_m) / 2.0
        if profile.curve.representation is PaceCurveRepresentation.CONSTANT_SPEED:
            # Piecewise-constant segments are discontinuous at their shared boundary.
            # Endpoint sampling would invent a linear ramp across the first interval
            # after that boundary. The interval midpoint selects its owning segment.
            pace = _speed_to_pace(evaluable.speed_at(mid))
            p_start = pace
            p_end = pace
        else:
            p_start = _speed_to_pace(evaluable.speed_at(from_m))
            p_end = _speed_to_pace(evaluable.speed_at(to_m))
        duration = length * (p_start + p_end) / 200.0
        if not _finite(duration) or duration <= 0.0:
            raise InvalidPaceCurveError(
                f"interval [{from_m}, {to_m}] produced non-finite/non-positive duration"
            )
        intervals.append(
            PaceInterval(
                fromM=from_m,
                toM=to_m,
                startPaceSecPer100M=p_start,
                endPaceSecPer100M=p_end,
                mode="continuous_curve",
                activeDurationSec=duration,
                blockIndex=0,
                repeatIndex=0,
                segmentIndex=i,
                startMode=resolved_start_mode.value,
                profileId=profile.profileId,
                profileSource=profile.source.value,
                profileType=profile.profileType.value,
                phaseType=None,
                continuousPhaseIndex=_phase_index_at(profile, mid),
                curveSegmentIndex=_segment_index_at(profile.curve.representation, evaluable, mid),
                curveRepresentation=profile.curve.representation.value,
                curveProfileVersion=profile.profileVersion,
            )
        )
    return intervals


def _scale_intervals(intervals: list[PaceInterval], factor: float) -> list[PaceInterval]:
    """Scale pace (and thus duration) of each interval by ``factor`` (velocity /= factor)."""
    from dataclasses import replace

    scaled: list[PaceInterval] = []
    for iv in intervals:
        new_start = iv.startPaceSecPer100M * factor
        new_end = iv.endPaceSecPer100M * factor
        new_duration = iv.activeDurationSec * factor
        if not (_finite(new_start) and _finite(new_end) and _finite(new_duration)):
            raise InvalidPaceCurveError("reconciliation produced a non-finite pace/duration")
        if new_start <= 0.0 or new_end <= 0.0:
            raise InvalidPaceCurveError("reconciliation produced a non-positive pace")
        scaled.append(
            replace(
                iv,
                startPaceSecPer100M=new_start,
                endPaceSecPer100M=new_end,
                activeDurationSec=new_duration,
            )
        )
    return scaled


def _region_duration(intervals: list[PaceInterval]) -> float:
    return sum(iv.activeDurationSec for iv in intervals)


def _reconcile(
    profile: ApprovedContinuousPaceProfile,
    intervals: list[PaceInterval],
    total: float,
) -> tuple[list[PaceInterval], float, tuple[ScaledRegion, ...]]:
    """Scale locked-split regions to their targets, then the remainder to the total.

    Returns the reconciled intervals, the worst per-split reconciliation error (sec) and
    the per-distance-span pace scale factors (for the post-reconciliation analytic bound
    re-check, §2.6). Locked-split targets are never modified; the total is never silently
    changed. Negative remaining time, non-finite or non-positive speeds are rejected (no
    clamping).
    """
    target_total = profile.targetTimeConstraint.targetTotalTimeSec
    locked = [s for s in profile.splitTimeConstraints if s.lockedByCoach]

    def in_region(iv: PaceInterval, from_m: float, to_m: float) -> bool:
        return iv.fromM >= from_m - _GEOM_TOL and iv.toM <= to_m + _GEOM_TOL

    # index intervals by identity for stable rebuild
    remaining_target = target_total
    reconciled: list[PaceInterval | None] = list(intervals)
    max_split_err = 0.0
    interval_factor: list[float] = [1.0] * len(intervals)

    for split in sorted(locked, key=lambda s: s.fromM):
        region_idx = [i for i, iv in enumerate(intervals) if in_region(iv, split.fromM, split.toM)]
        if not region_idx:
            raise ProfileCompilationError(
                f"locked split {split.splitIndex} has no compiled intervals"
            )
        region = [intervals[i] for i in region_idx]
        current = _region_duration(region)
        if current <= 0.0:
            raise ProfileCompilationError(f"locked split {split.splitIndex} has zero duration")
        factor = split.targetDurationSec / current
        scaled = _scale_intervals(region, factor)
        for local_i, global_i in enumerate(region_idx):
            reconciled[global_i] = scaled[local_i]
            interval_factor[global_i] = factor
        achieved = _region_duration(scaled)
        max_split_err = max(max_split_err, abs(achieved - split.targetDurationSec))
        remaining_target -= split.targetDurationSec

    if remaining_target < -CURVE_TIME_TOLERANCE_SEC:
        raise ProfileCompilationError(
            f"locked split targets exceed the total: remaining {remaining_target} s < 0"
        )

    # scale the non-locked remainder to the remaining target
    locked_regions = [(s.fromM, s.toM) for s in locked]

    def is_locked_interval(iv: PaceInterval) -> bool:
        return any(in_region(iv, f, t) for f, t in locked_regions)

    remainder_idx = [i for i, iv in enumerate(intervals) if not is_locked_interval(iv)]
    if remainder_idx:
        remainder = [reconciled[i] for i in remainder_idx]
        assert all(r is not None for r in remainder)
        current_remainder = _region_duration([r for r in remainder if r is not None])
        if current_remainder <= 0.0:
            if remaining_target > CURVE_TIME_TOLERANCE_SEC:
                raise ProfileCompilationError("no remainder region to absorb remaining time")
        else:
            if remaining_target <= 0.0:
                raise ProfileCompilationError(
                    "remaining target time must be positive for the unlocked region"
                )
            factor = remaining_target / current_remainder
            scaled_remainder = _scale_intervals([r for r in remainder if r is not None], factor)
            for local_i, global_i in enumerate(remainder_idx):
                reconciled[global_i] = scaled_remainder[local_i]
                interval_factor[global_i] = factor
    elif abs(remaining_target) > CURVE_TIME_TOLERANCE_SEC:
        raise ProfileCompilationError(
            "all distance is locked but locked totals do not equal the target"
        )

    final = [iv for iv in reconciled if iv is not None]
    # merge consecutive intervals sharing a factor into ScaledRegion spans
    regions: list[ScaledRegion] = []
    pairs = [
        (iv, factor)
        for iv, factor in zip(reconciled, interval_factor, strict=True)
        if iv is not None
    ]
    for iv, factor in pairs:
        if regions and abs(regions[-1].paceScaleFactor - factor) <= 1e-15:
            regions[-1] = ScaledRegion(regions[-1].fromM, iv.toM, factor)
        else:
            regions.append(ScaledRegion(iv.fromM, iv.toM, factor))
    return final, max_split_err, tuple(regions)


def _check_physical_bounds(
    evaluable: EvaluableCurve,
    breakpoints: tuple[float, ...],
    ctx: ContinuousCurveValidationContext,
) -> None:
    """Check speed/acceleration/gradient bounds at breakpoints and knot-interval samples.

    Acceleration uses a = v * dv/dx. Evaluated at every breakpoint (which already includes
    knots) and does not hide violations behind coarse sampling.
    """
    for d in breakpoints:
        speed = evaluable.speed_at(d)
        if ctx.minimumSpeedMps is not None and speed < ctx.minimumSpeedMps - 1e-9:
            raise ProfileCompilationError(
                f"speed {speed} at {d} m below minimum {ctx.minimumSpeedMps}"
            )
        if ctx.maximumSpeedMps is not None and speed > ctx.maximumSpeedMps + 1e-9:
            raise ProfileCompilationError(
                f"speed {speed} at {d} m above maximum {ctx.maximumSpeedMps}"
            )
        grad = evaluable.gradient_at(d)
        if (
            ctx.maximumSpeedGradientPerM is not None
            and abs(grad) > ctx.maximumSpeedGradientPerM + 1e-9
        ):
            raise ProfileCompilationError(
                f"speed gradient {grad} at {d} m exceeds max {ctx.maximumSpeedGradientPerM}"
            )
        accel = speed * grad
        if ctx.maximumAccelerationMps2 is not None and accel > ctx.maximumAccelerationMps2 + 1e-9:
            raise ProfileCompilationError(
                f"acceleration {accel} at {d} m exceeds max {ctx.maximumAccelerationMps2}"
            )
        if ctx.maximumDecelerationMps2 is not None and -accel > ctx.maximumDecelerationMps2 + 1e-9:
            raise ProfileCompilationError(
                f"deceleration {-accel} at {d} m exceeds max {ctx.maximumDecelerationMps2}"
            )


def compile_continuous_pace_profile(
    profile: ApprovedContinuousPaceProfile,
    *,
    pool_length_m: int,
    resolved_start_mode: StartMode,
    stroke: Stroke,
    total_distance_m: float,
    validation_context: ContinuousCurveValidationContext | None = None,
) -> CompiledContinuousPacePlan:
    """Compile an approved continuous profile into a reconciled ``PaceTimeline``."""
    if not profile.is_live_eligible:
        raise ProfileCompilationError(
            f"profile {profile.profileId} is not live-eligible "
            f"(approvalStatus={profile.approvalStatus})"
        )
    if profile.poolLengthM != pool_length_m:
        raise ProfileCompilationError(
            f"profile pool {profile.poolLengthM} != workout pool {pool_length_m}"
        )
    if profile.startMode is not resolved_start_mode:
        raise ProfileCompilationError(
            f"profile start mode {profile.startMode} != resolved {resolved_start_mode}"
        )
    if profile.stroke is not stroke:
        raise ProfileCompilationError(f"profile stroke {profile.stroke} != workout stroke {stroke}")
    if abs(profile.totalDistanceM - total_distance_m) > _GEOM_TOL:
        raise ProfileCompilationError(
            f"profile covers {profile.totalDistanceM} m, workout total is {total_distance_m} m"
        )

    total = profile.totalDistanceM
    evaluable = build_evaluable_curve(profile.curve)
    breakpoints = _deterministic_breakpoints(profile, evaluable, total)

    # physical bounds BEFORE reconciliation: the analytic critical-point verifier is
    # authoritative (§2.7); the breakpoint-grid pass is additional validation only.
    has_bounds = validation_context is not None and validation_context.has_any_bound
    if has_bounds:
        assert validation_context is not None
        check_curve_physical_bounds(evaluable, validation_context, stage="pre-reconciliation")
        _check_physical_bounds(evaluable, breakpoints, validation_context)

    raw = _raw_intervals(profile, evaluable, breakpoints, resolved_start_mode)
    reconciled, max_split_err, scaled_regions = _reconcile(profile, raw, total)

    integrated_total = _region_duration(reconciled)
    target_total = profile.targetTimeConstraint.targetTotalTimeSec
    total_err = abs(integrated_total - target_total)

    tol = max(profile.targetTimeConstraint.toleranceSec, CURVE_TIME_TOLERANCE_SEC)
    # Post-reconciliation physical bound re-check (§2.6): scaling changed speed, gradient
    # AND acceleration, so ALL supplied bounds are re-verified analytically on the scaled
    # curve — reject, never clamp. `physicalBoundsChecked=True` is written only when the
    # reconciled final timeline really passed every supplied bound (a violation raises).
    physical_checked = False
    if has_bounds:
        assert validation_context is not None
        check_curve_physical_bounds(
            evaluable,
            validation_context,
            regions=scaled_regions,
            stage="post-reconciliation",
        )
        _recheck_reconciled_bounds(reconciled, validation_context)
        physical_checked = True

    speeds = []
    for iv in reconciled:
        speeds.append(100.0 / iv.startPaceSecPer100M)
        speeds.append(100.0 / iv.endPaceSecPer100M)
    min_speed = min(speeds)
    max_speed = max(speeds)

    validation_passed = (
        total_err <= tol
        and max_split_err <= tol
        and min_speed > 0.0
        and _finite(min_speed)
        and _finite(max_speed)
    )

    summary = CurveValidationSummary(
        integratedTotalTimeSec=integrated_total,
        targetTotalTimeSec=target_total,
        totalReconciliationErrorSec=total_err,
        maxSplitReconciliationErrorSec=max_split_err,
        minTargetSpeedMps=min_speed,
        maxTargetSpeedMps=max_speed,
        phaseCount=len(profile.phases),
        knotCount=len(profile.curve.knots),
        compiledIntervalCount=len(reconciled),
        representation=profile.curve.representation,
        compilerVersion=CONTINUOUS_COMPILER_VERSION,
        lookupResolutionM=CONTINUOUS_CURVE_MAX_STEP_M,
        physicalBoundsChecked=physical_checked,
        validationPassed=validation_passed,
    )

    if not validation_passed:
        raise ProfileCompilationError(
            f"continuous profile failed reconciliation: total error {total_err} s, "
            f"max split error {max_split_err} s (tolerance {tol} s)"
        )

    timeline = PaceTimeline(
        totalDistanceM=total,
        totalActiveDurationSec=integrated_total,
        intervals=tuple(reconciled),
    )
    return CompiledContinuousPacePlan(
        timeline=timeline,
        validationSummary=summary,
        profileId=profile.profileId,
        profileVersion=profile.profileVersion,
        profileSource=profile.source,
        profileType=profile.profileType,
    )


def _recheck_reconciled_bounds(
    intervals: list[PaceInterval],
    ctx: ContinuousCurveValidationContext,
) -> None:
    for iv in intervals:
        for pace in (iv.startPaceSecPer100M, iv.endPaceSecPer100M):
            speed = 100.0 / pace
            if ctx.minimumSpeedMps is not None and speed < ctx.minimumSpeedMps - 1e-9:
                raise ProfileCompilationError(
                    f"reconciled speed {speed} below minimum {ctx.minimumSpeedMps}"
                )
            if ctx.maximumSpeedMps is not None and speed > ctx.maximumSpeedMps + 1e-9:
                raise ProfileCompilationError(
                    f"reconciled speed {speed} above maximum {ctx.maximumSpeedMps}"
                )


def compile_approved_pace_profile_with_summary(
    profile: ApprovedContinuousPaceProfile,
    *,
    pool_length_m: int,
    resolved_start_mode: StartMode,
    stroke: Stroke,
    total_distance_m: float,
    validation_context: ContinuousCurveValidationContext | None = None,
) -> CompiledContinuousPacePlan:
    """Alias for :func:`compile_continuous_pace_profile` (name parity with ADR-038 §16)."""
    return compile_continuous_pace_profile(
        profile,
        pool_length_m=pool_length_m,
        resolved_start_mode=resolved_start_mode,
        stroke=stroke,
        total_distance_m=total_distance_m,
        validation_context=validation_context,
    )


__all__ = [
    "CONTINUOUS_COMPILER_VERSION",
    "CONTINUOUS_CURVE_MAX_STEP_M",
    "CURVE_TIME_TOLERANCE_SEC",
    "CompiledContinuousPacePlan",
    "compile_approved_pace_profile_with_summary",
    "compile_continuous_pace_profile",
]
