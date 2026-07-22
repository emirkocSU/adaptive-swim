"""Official wall-split analysis and aggregate target adherence metrics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from analytics._math import mean, overlap_ms, rms
from analytics.stops import lifecycle_pause_intervals, stop_pause_intervals
from analytics.types import (
    ApprovedPaceProfileVersion,
    ProfileRuntimeContext,
    ReportBuildContext,
)
from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.enums import EventType
from contracts.events import (
    CoachPacingResetAppliedPayload,
    EventEnvelope,
    SessionCreatedPayload,
    StopPauseStartedPayload,
)
from contracts.session_report import (
    AheadBehindStatus,
    MetricStatus,
    SplitAggregateMetrics,
    SplitAnalysis,
    SplitPerformance,
)
from swimcore.pacing.timeline import target_active_time_at_distance
from swimcore.pacing.types import PaceTimeline
from swimcore.replay.state import HistoricalSessionState


@dataclass(frozen=True, slots=True)
class _ProfilePeriod:
    effectiveFromLength: int
    profileId: str | None
    profileVersion: str | None
    profileSource: str | None
    profileType: str | None
    coachLocked: bool | None
    profile: ApprovedPaceProfileVersion | None
    timeline: PaceTimeline | None


@dataclass(frozen=True, slots=True)
class SplitBuildResult:
    analysis: SplitAnalysis
    eligibleActualSpeeds: tuple[float, ...]
    eligibleTargetSpeeds: tuple[float, ...]
    eligibleSplitIndices: tuple[int, ...]
    allActiveDurations: tuple[float, ...]


def _profile_periods(
    state: HistoricalSessionState,
    events: Sequence[EventEnvelope],
    pace_profile: ApprovedPaceProfileVersion | None,
    compiled_timeline: PaceTimeline | None,
    registry: Mapping[tuple[str, str], ProfileRuntimeContext],
) -> tuple[_ProfilePeriod, ...]:
    created: SessionCreatedPayload | None = None
    for event in events:
        if event.type is EventType.SessionCreated:
            payload = event.payload
            assert isinstance(payload, SessionCreatedPayload)
            created = payload
            break
    current_profile = pace_profile
    current_timeline = compiled_timeline
    current_id = (
        pace_profile.profileId
        if pace_profile is not None
        else (
            created.selectedPaceProfileId
            if created is not None and created.selectedPaceProfileId is not None
            else state.selectedPaceProfileId
        )
    )
    current_version = (
        pace_profile.profileVersion
        if pace_profile is not None
        else (
            created.selectedPaceProfileVersion
            if created is not None and created.selectedPaceProfileVersion is not None
            else state.selectedPaceProfileVersion
        )
    )
    current_source = (
        pace_profile.source.value
        if pace_profile is not None
        else (
            created.selectedPaceProfileSource
            if created is not None and created.selectedPaceProfileSource is not None
            else state.selectedPaceProfileSource
        )
    )
    current_type = (
        pace_profile.profileType.value
        if pace_profile is not None
        else (
            created.selectedPaceProfileType
            if created is not None and created.selectedPaceProfileType is not None
            else state.selectedPaceProfileType
        )
    )
    current_locked: bool | None = (
        pace_profile.coachLocked
        if pace_profile is not None
        else (
            created.profileCoachLocked
            if created is not None and created.selectedPaceProfileId is not None
            else state.profileCoachLocked
        )
    )
    periods = [
        _ProfilePeriod(
            effectiveFromLength=0,
            profileId=current_id,
            profileVersion=current_version,
            profileSource=current_source,
            profileType=current_type,
            coachLocked=current_locked,
            profile=current_profile,
            timeline=current_timeline,
        )
    ]
    for event in events:
        if event.type is not EventType.CoachPacingResetApplied:
            continue
        payload = event.payload
        assert isinstance(payload, CoachPacingResetAppliedPayload)
        if payload.replacementPaceProfileId is None:
            continue
        key = (payload.replacementPaceProfileId, payload.replacementPaceProfileVersion or "")
        runtime = registry.get(key)
        current_profile = runtime.profile if runtime is not None else None
        current_timeline = runtime.timeline if runtime is not None else None
        periods.append(
            _ProfilePeriod(
                effectiveFromLength=payload.effectiveFromLength,
                profileId=payload.replacementPaceProfileId,
                profileVersion=payload.replacementPaceProfileVersion,
                profileSource=payload.replacementPaceProfileSource,
                profileType=payload.replacementPaceProfileType,
                coachLocked=payload.replacementProfileCoachLocked,
                profile=current_profile,
                timeline=current_timeline,
            )
        )
    return tuple(sorted(periods, key=lambda item: item.effectiveFromLength))


def _period_for_split(periods: Sequence[_ProfilePeriod], split_index: int) -> _ProfilePeriod:
    selected = periods[0]
    for period in periods:
        if period.effectiveFromLength <= split_index:
            selected = period
        else:
            break
    return selected


def _locked_target(
    profile: ApprovedPaceProfileVersion | None, from_m: float, to_m: float
) -> float | None:
    if isinstance(profile, ApprovedContinuousPaceProfile):
        for item in profile.splitTimeConstraints:
            if (
                item.lockedByCoach
                and abs(item.fromM - from_m) <= 1e-6
                and abs(item.toM - to_m) <= 1e-6
            ):
                return item.targetDurationSec
    return None


def _target_duration(period: _ProfilePeriod, from_m: float, to_m: float) -> float | None:
    locked = _locked_target(period.profile, from_m, to_m)
    if locked is not None:
        return locked
    if period.timeline is None:
        return None
    if to_m > period.timeline.totalDistanceM + 1e-6:
        return None
    start = target_active_time_at_distance(period.timeline, from_m).elapsedActiveSec
    end = target_active_time_at_distance(period.timeline, to_m).elapsedActiveSec
    return max(0.0, end - start)


def _phase_types(period: _ProfilePeriod, from_m: float, to_m: float) -> tuple[str, ...]:
    if period.timeline is None:
        return ()
    phases: list[str] = []
    for interval in period.timeline.intervals:
        if interval.toM <= from_m + 1e-9 or interval.fromM >= to_m - 1e-9:
            continue
        if interval.phaseType is not None and interval.phaseType not in phases:
            phases.append(interval.phaseType)
    return tuple(phases)


def _unreliable_stop_reasons(
    events: Sequence[EventEnvelope], start_ms: int, end_ms: int
) -> tuple[str, ...]:
    reasons: list[str] = []
    for event in events:
        if event.type is not EventType.StopPauseStarted:
            continue
        payload = event.payload
        assert isinstance(payload, StopPauseStartedPayload)
        stop_end = payload.endedAtMs or end_ms
        if overlap_ms(start_ms, end_ms, payload.startedAtMs, stop_end) <= 0:
            continue
        if payload.stopStartTimeQuality.value in {"LOW", "UNKNOWN"}:
            reasons.append("UNRELIABLE_STOP_TIMING")
        if payload.alignmentQuality.value in {"LOW", "UNKNOWN"}:
            reasons.append("UNRELIABLE_ALIGNMENT")
    return tuple(dict.fromkeys(reasons))


def build_split_analysis(
    *,
    replay_state: HistoricalSessionState,
    events: Sequence[EventEnvelope],
    pace_profile: ApprovedPaceProfileVersion | None,
    compiled_timeline: PaceTimeline | None,
    report_context: ReportBuildContext,
) -> SplitBuildResult:
    pool = replay_state.poolLengthM
    started_at = replay_state.startedAtMs
    if pool is None or started_at is None:
        empty_aggregate = SplitAggregateMetrics(
            status=MetricStatus.INSUFFICIENT_DATA,
            eligibleSplitCount=0,
            excludedSplitCount=len(replay_state.recordedSplits),
        )
        return SplitBuildResult(
            analysis=SplitAnalysis(
                status=MetricStatus.INSUFFICIENT_DATA,
                splits=(),
                aggregate=empty_aggregate,
            ),
            eligibleActualSpeeds=(),
            eligibleTargetSpeeds=(),
            eligibleSplitIndices=(),
            allActiveDurations=(),
        )

    periods = _profile_periods(
        replay_state,
        events,
        pace_profile,
        compiled_timeline,
        report_context.profileRegistry,
    )
    horizon = replay_state.endedAtMs or replay_state.lastEventTimestampMs
    stop_intervals = stop_pause_intervals(replay_state, horizon)
    lifecycle_intervals = lifecycle_pause_intervals(events, horizon)
    verified = {item.lengthIndex: item for item in replay_state.verifiedSplits}

    outputs: list[SplitPerformance] = []
    target_cumulative = 0.0
    actual_cumulative = 0.0
    eligible_errors: list[float] = []
    eligible_error_pct: list[float] = []
    eligible_actual_speeds: list[float] = []
    eligible_target_speeds: list[float] = []
    eligible_indices: list[int] = []
    nonexcluded_active_durations: list[float] = []
    all_active_durations: list[float] = []

    previous_wall = started_at
    for split in replay_state.recordedSplits:
        split_index = split.lengthIndex
        actual_end = split.wallTimestampMs
        actual_start = previous_wall
        previous_wall = actual_end
        elapsed_ms = actual_end - actual_start
        stopped_ms = sum(
            overlap_ms(actual_start, actual_end, interval.startMs, interval.endMs)
            for interval in stop_intervals
        )
        paused_ms = sum(
            overlap_ms(actual_start, actual_end, interval.startMs, interval.endMs)
            for interval in lifecycle_intervals
        )
        active_ms = elapsed_ms - stopped_ms - paused_ms
        if active_ms < 0:
            active_ms = 0
        actual_duration = active_ms / 1000.0
        stopped_duration = stopped_ms / 1000.0
        paused_duration = paused_ms / 1000.0
        elapsed_duration = elapsed_ms / 1000.0
        actual_cumulative += actual_duration
        all_active_durations.append(actual_duration)

        from_m = float(split_index * pool)
        to_m = float((split_index + 1) * pool)
        distance = to_m - from_m
        actual_speed = distance / actual_duration if actual_duration > 0 else None
        period = _period_for_split(periods, split_index)
        target_duration = _target_duration(period, from_m, to_m)
        target_status = (
            MetricStatus.AVAILABLE if target_duration is not None else MetricStatus.MISSING_TARGET
        )
        target_speed = (
            distance / target_duration
            if target_duration is not None and target_duration > 0
            else None
        )
        if target_duration is not None:
            target_cumulative += target_duration
        duration_delta = actual_duration - target_duration if target_duration is not None else None
        duration_delta_pct = (
            duration_delta / target_duration * 100.0
            if duration_delta is not None and target_duration is not None and target_duration > 0
            else None
        )
        cumulative_delta = (
            actual_cumulative - target_cumulative if target_duration is not None else None
        )
        speed_delta = (
            actual_speed - target_speed
            if actual_speed is not None and target_speed is not None
            else None
        )

        quality_flags = [split.qualityFlag]
        verification = verified.get(split_index)
        if verification is not None:
            quality_flags.append(f"VERIFIED_BY_{verification.verificationSource}")
        exclusion_reasons: list[str] = []
        if split.qualityFlag == "INVALID":
            exclusion_reasons.append("INVALID_SPLIT_QUALITY")
        if split.source == "WEARABLE" and verification is None:
            exclusion_reasons.append("UNVERIFIED_WEARABLE_WALL")
        exclusion_reasons.extend(_unreliable_stop_reasons(events, actual_start, actual_end))
        excluded = bool(exclusion_reasons)

        if duration_delta is None:
            ahead_behind = AheadBehindStatus.NOT_AVAILABLE
        elif abs(duration_delta) <= report_context.adherenceToleranceSec:
            ahead_behind = AheadBehindStatus.ON_TARGET
        elif duration_delta < 0:
            ahead_behind = AheadBehindStatus.AHEAD
        else:
            ahead_behind = AheadBehindStatus.BEHIND

        if not excluded:
            nonexcluded_active_durations.append(actual_duration)
        if not excluded and target_duration is not None:
            eligible_errors.append(duration_delta or 0.0)
            eligible_error_pct.append(abs(duration_delta_pct or 0.0))
            eligible_indices.append(split_index)
            if actual_speed is not None:
                eligible_actual_speeds.append(actual_speed)
            if target_speed is not None:
                eligible_target_speeds.append(target_speed)

        outputs.append(
            SplitPerformance(
                splitIndex=split_index,
                fromM=from_m,
                toM=to_m,
                distanceM=distance,
                actualStartTimeMs=actual_start,
                actualEndTimeMs=actual_end,
                elapsedDurationSec=elapsed_duration,
                stoppedDurationSec=stopped_duration,
                lifecyclePausedDurationSec=paused_duration,
                actualDurationSec=actual_duration,
                actualCumulativeTimeSec=actual_cumulative,
                actualSpeedMps=actual_speed,
                targetDurationSec=target_duration,
                targetCumulativeTimeSec=(
                    target_cumulative if target_duration is not None else None
                ),
                targetSpeedMps=target_speed,
                durationDeltaSec=duration_delta,
                durationDeltaPct=duration_delta_pct,
                cumulativeDeltaSec=cumulative_delta,
                speedDeltaMps=speed_delta,
                aheadBehindStatus=ahead_behind,
                splitSource=split.source,
                qualityFlags=tuple(quality_flags),
                excludedFromAggregateMetrics=excluded,
                exclusionReasons=tuple(dict.fromkeys(exclusion_reasons)),
                profileId=period.profileId,
                profileVersion=period.profileVersion,
                profileSource=period.profileSource,
                profileType=period.profileType,
                curvePhaseTypes=_phase_types(period, from_m, to_m),
                targetStatus=target_status,
            )
        )

    excluded_count = sum(1 for item in outputs if item.excludedFromAggregateMetrics)
    if eligible_errors:
        positives = [value for value in eligible_errors if value > 0]
        negatives = [value for value in eligible_errors if value < 0]
        on_target = sum(
            1 for value in eligible_errors if abs(value) <= report_context.adherenceToleranceSec
        )
        first_half_time: float | None = None
        second_half_time: float | None = None
        half_delta: float | None = None
        half_pct: float | None = None
        if len(nonexcluded_active_durations) >= 2:
            midpoint = len(nonexcluded_active_durations) // 2
            if midpoint > 0 and len(nonexcluded_active_durations) - midpoint > 0:
                first_half_time = math.fsum(nonexcluded_active_durations[:midpoint])
                second_half_time = math.fsum(nonexcluded_active_durations[midpoint:])
                half_delta = second_half_time - first_half_time
                if first_half_time > 0:
                    half_pct = half_delta / first_half_time * 100.0
        aggregate = SplitAggregateMetrics(
            status=MetricStatus.AVAILABLE,
            eligibleSplitCount=len(eligible_errors),
            excludedSplitCount=excluded_count,
            meanAbsoluteSplitErrorSec=mean([abs(value) for value in eligible_errors]),
            meanAbsoluteSplitPercentageError=mean(eligible_error_pct),
            rootMeanSquaredSplitErrorSec=rms(eligible_errors),
            maximumPositiveSplitErrorSec=max(positives) if positives else None,
            maximumNegativeSplitErrorSec=min(negatives) if negatives else None,
            targetPaceAdherenceRatio=on_target / len(eligible_errors),
            onTargetSplitRatio=on_target / len(eligible_errors),
            firstHalfTimeSec=first_half_time,
            secondHalfTimeSec=second_half_time,
            firstHalfSecondHalfDeltaSec=half_delta,
            firstHalfSecondHalfDeltaPct=half_pct,
        )
        status = MetricStatus.AVAILABLE
    else:
        aggregate = SplitAggregateMetrics(
            status=(
                MetricStatus.MISSING_TARGET
                if outputs and all(item.targetDurationSec is None for item in outputs)
                else MetricStatus.INSUFFICIENT_DATA
            ),
            eligibleSplitCount=0,
            excludedSplitCount=excluded_count,
        )
        status = aggregate.status

    return SplitBuildResult(
        analysis=SplitAnalysis(status=status, splits=tuple(outputs), aggregate=aggregate),
        eligibleActualSpeeds=tuple(eligible_actual_speeds),
        eligibleTargetSpeeds=tuple(eligible_target_speeds),
        eligibleSplitIndices=tuple(eligible_indices),
        allActiveDurations=tuple(all_active_durations),
    )
