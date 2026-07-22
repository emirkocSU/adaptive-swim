"""Pacing shape/fade classification and coach-reset provenance analysis."""

from __future__ import annotations

import math
from collections.abc import Sequence

from analytics._math import least_squares_slope, mean
from analytics.splits import SplitBuildResult
from analytics.types import ApprovedPaceProfileVersion, ReportBuildContext
from contracts.enums import EventType
from contracts.events import (
    CoachPacingResetAppliedPayload,
    CoachPacingResetRequestedPayload,
    EventEnvelope,
)
from contracts.session_report import (
    CoachResetAnalysis,
    CoachResetSummary,
    MetricStatus,
    PaceFadeAnalysis,
    PacingAnalysis,
    PacingShapeClass,
)


def _shape(speeds: Sequence[float], minimum_splits: int, threshold_pct: float) -> PacingShapeClass:
    if len(speeds) < minimum_splits:
        return PacingShapeClass.INSUFFICIENT_DATA
    midpoint = len(speeds) // 2
    if midpoint == 0:
        return PacingShapeClass.INSUFFICIENT_DATA
    first = mean(speeds[:midpoint])
    second = mean(speeds[midpoint:])
    if first <= 0:
        return PacingShapeClass.INSUFFICIENT_DATA
    delta_pct = (second - first) / first * 100.0
    increasing_steps = sum(
        1 for left, right in zip(speeds, speeds[1:], strict=False) if right > left
    )
    decreasing_steps = sum(
        1 for left, right in zip(speeds, speeds[1:], strict=False) if right < left
    )
    reversals = 0
    previous_sign = 0
    for left, right in zip(speeds, speeds[1:], strict=False):
        sign = 1 if right > left else -1 if right < left else 0
        if sign and previous_sign and sign != previous_sign:
            reversals += 1
        if sign:
            previous_sign = sign
    if reversals >= max(2, len(speeds) // 2):
        return PacingShapeClass.IRREGULAR
    if abs(delta_pct) <= threshold_pct:
        return PacingShapeClass.EVEN
    if delta_pct > threshold_pct:
        if increasing_steps >= len(speeds) - 2:
            return PacingShapeClass.PROGRESSIVE
        return PacingShapeClass.NEGATIVE
    if decreasing_steps >= len(speeds) - 2:
        return PacingShapeClass.POSITIVE_FADE
    return PacingShapeClass.IRREGULAR


def _fade_pct(speeds: Sequence[float]) -> float | None:
    if len(speeds) < 2 or speeds[0] <= 0:
        return None
    return (speeds[-1] - speeds[0]) / speeds[0] * 100.0


def _decline_start(speeds: Sequence[float], context: ReportBuildContext) -> int | None:
    required = context.minimumConsecutiveDecliningSplits
    if len(speeds) < required + 1 or speeds[0] <= 0:
        return None
    reference = speeds[0]
    for start in range(1, len(speeds) - required + 1):
        window = speeds[start : start + required]
        declines = [(reference - value) / reference * 100.0 for value in window]
        sustained = all(value >= context.minimumDeclinePct for value in declines)
        non_recovering = all(
            right <= left + 1e-12 for left, right in zip(window, window[1:], strict=False)
        )
        if sustained and non_recovering:
            return start
    return None


def build_pacing_analysis(
    split_result: SplitBuildResult,
    context: ReportBuildContext,
) -> PacingAnalysis:
    actual = split_result.eligibleActualSpeeds
    target = split_result.eligibleTargetSpeeds
    actual_fade = _fade_pct(actual)
    expected_fade = _fade_pct(target)
    slope = None
    if len(actual) >= 2:
        xs = [index / (len(actual) - 1) for index in range(len(actual))]
        slope = least_squares_slope(xs, actual)
    decline = _decline_start(actual, context)
    collapse: bool | None = None
    collapse_delta: float | None = None
    if actual_fade is not None and expected_fade is not None and len(actual) >= 3:
        collapse_delta = actual_fade - expected_fade
        collapse = collapse_delta < -context.unexpectedCollapseMarginPct
    fade_status = (
        MetricStatus.AVAILABLE if actual_fade is not None else MetricStatus.INSUFFICIENT_DATA
    )
    warnings: list[str] = []
    if collapse:
        warnings.append("UNEXPECTED_PACING_COLLAPSE_ADVISORY")
    return PacingAnalysis(
        status=fade_status,
        targetPacingShape=_shape(
            target, context.minimumPacingShapeSplits, context.onTargetTolerancePct
        ),
        actualPacingShape=_shape(
            actual, context.minimumPacingShapeSplits, context.onTargetTolerancePct
        ),
        fade=PaceFadeAnalysis(
            status=fade_status,
            expectedPaceFadePct=expected_fade,
            actualPaceFadePct=actual_fade,
            paceDeclineStartSplit=(
                split_result.eligibleSplitIndices[decline] if decline is not None else None
            ),
            paceDeclineSlope=slope,
            unexpectedCollapse=collapse,
            unexpectedCollapseDeltaPct=collapse_delta,
        ),
        eligibleSpeedSeriesMps=actual,
        warningCodes=tuple(warnings),
    )


def build_coach_reset_analysis(
    events: Sequence[EventEnvelope],
    initial_profile: ApprovedPaceProfileVersion | None,
    pool_length_m: int | None,
) -> CoachResetAnalysis:
    pending: list[tuple[CoachPacingResetRequestedPayload, int]] = []
    resets: list[CoachResetSummary] = []
    current_id = initial_profile.profileId if initial_profile is not None else None
    current_version = initial_profile.profileVersion if initial_profile is not None else None
    current_source = initial_profile.source.value if initial_profile is not None else None
    current_type = initial_profile.profileType.value if initial_profile is not None else None
    current_locked = initial_profile.coachLocked if initial_profile is not None else None
    requested_count = 0
    applied_count = 0
    safe_wall_count = 0

    for event in events:
        if event.type is EventType.CoachPacingResetRequested:
            payload = event.payload
            assert isinstance(payload, CoachPacingResetRequestedPayload)
            pending.append((payload, event.tsMs))
            requested_count += 1
        elif event.type is EventType.CoachPacingResetApplied:
            payload = event.payload
            assert isinstance(payload, CoachPacingResetAppliedPayload)
            applied_count += 1
            requested_payload, requested_at = pending.pop(0) if pending else (None, event.tsMs)
            wall_distance = (
                float(payload.effectiveFromLength * pool_length_m)
                if pool_length_m is not None
                else None
            )
            if wall_distance is not None and pool_length_m:
                lengths = wall_distance / pool_length_m
                if math.isclose(lengths, round(lengths), abs_tol=1e-9):
                    safe_wall_count += 1
            replacement_id = payload.replacementPaceProfileId or (
                requested_payload.replacementPaceProfileId
                if requested_payload is not None
                else None
            )
            replacement_version = payload.replacementPaceProfileVersion or (
                requested_payload.replacementPaceProfileVersion
                if requested_payload is not None
                else None
            )
            resets.append(
                CoachResetSummary(
                    resetIndex=len(resets),
                    requestedAtMs=requested_at,
                    appliedAtMs=event.tsMs,
                    appliedWallDistanceM=wall_distance,
                    previousProfileId=payload.previousPaceProfileId or current_id,
                    previousProfileVersion=payload.previousPaceProfileVersion or current_version,
                    previousProfileSource=current_source,
                    previousProfileType=current_type,
                    previousCoachLocked=current_locked,
                    replacementProfileId=replacement_id,
                    replacementProfileVersion=replacement_version,
                    replacementProfileSource=payload.replacementPaceProfileSource,
                    replacementProfileType=payload.replacementPaceProfileType,
                    replacementCoachLocked=payload.replacementProfileCoachLocked,
                )
            )
            if replacement_id is not None:
                current_id = replacement_id
                current_version = replacement_version
                current_source = payload.replacementPaceProfileSource
                current_type = payload.replacementPaceProfileType
                current_locked = payload.replacementProfileCoachLocked

    for requested_payload, requested_at in pending:
        resets.append(
            CoachResetSummary(
                resetIndex=len(resets),
                requestedAtMs=requested_at,
                replacementProfileId=requested_payload.replacementPaceProfileId,
                replacementProfileVersion=requested_payload.replacementPaceProfileVersion,
                replacementProfileSource=requested_payload.replacementPaceProfileSource,
                replacementProfileType=requested_payload.replacementPaceProfileType,
                replacementCoachLocked=requested_payload.replacementProfileCoachLocked,
                previousProfileId=current_id,
                previousProfileVersion=current_version,
                previousProfileSource=current_source,
                previousProfileType=current_type,
                previousCoachLocked=current_locked,
            )
        )

    return CoachResetAnalysis(
        status=MetricStatus.AVAILABLE,
        coachResetRequestedCount=requested_count,
        coachResetAppliedCount=applied_count,
        pendingCoachResetCount=len(pending),
        safeWallApplicationCount=safe_wall_count,
        resets=tuple(resets),
    )
