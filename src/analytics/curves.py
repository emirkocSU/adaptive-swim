"""Trusted observation vs compiled target-curve comparison."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

from analytics._math import mean, overlap_ms, rms
from analytics.errors import ObservationValidationError
from analytics.stops import TimeInterval, lifecycle_pause_intervals, stop_pause_intervals
from analytics.types import (
    ApprovedPaceProfileVersion,
    ProfileRuntimeContext,
    ReportBuildContext,
    SessionObservation,
)
from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.enums import EventType
from contracts.events import CoachPacingResetAppliedPayload, EventEnvelope
from contracts.session_report import (
    ContinuousCurveAnalysis,
    MetricStatus,
    PhaseCurveDeviation,
)
from swimcore.pacing.timeline import (
    ghost_distance_at_active_time,
    target_active_time_at_distance,
)
from swimcore.pacing.types import PaceTimeline
from swimcore.replay.state import HistoricalSessionState


@dataclass(frozen=True, slots=True)
class _TargetPeriod:
    appliedAtMs: int
    effectiveDistanceM: float
    timeline: PaceTimeline
    profile: ApprovedPaceProfileVersion | None


@dataclass(frozen=True, slots=True)
class _ResolvedObservation:
    timestampMs: int
    estimatedDistanceM: float
    smoothedVelocityMps: float | None
    phaseType: str | None
    quality: str
    source: str


def _active_between(
    start_ms: int,
    end_ms: int,
    stops: Sequence[TimeInterval],
    pauses: Sequence[TimeInterval],
) -> int:
    if end_ms <= start_ms:
        return 0
    stopped = sum(overlap_ms(start_ms, end_ms, item.startMs, item.endMs) for item in stops)
    paused = sum(overlap_ms(start_ms, end_ms, item.startMs, item.endMs) for item in pauses)
    return max(0, end_ms - start_ms - stopped - paused)


def _target_periods(
    *,
    state: HistoricalSessionState,
    events: Sequence[EventEnvelope],
    pace_profile: ApprovedPaceProfileVersion | None,
    compiled_timeline: PaceTimeline | None,
    context: ReportBuildContext,
) -> tuple[_TargetPeriod, ...]:
    if compiled_timeline is None or state.startedAtMs is None:
        return ()
    periods = [
        _TargetPeriod(
            appliedAtMs=state.startedAtMs,
            effectiveDistanceM=0.0,
            timeline=compiled_timeline,
            profile=pace_profile,
        )
    ]
    pool = state.poolLengthM
    for event in events:
        if event.type is not EventType.CoachPacingResetApplied:
            continue
        payload = event.payload
        assert isinstance(payload, CoachPacingResetAppliedPayload)
        if payload.replacementPaceProfileId is None or pool is None:
            continue
        key = (payload.replacementPaceProfileId, payload.replacementPaceProfileVersion or "")
        runtime: ProfileRuntimeContext | None = context.profileRegistry.get(key)
        if runtime is None:
            continue
        periods.append(
            _TargetPeriod(
                appliedAtMs=event.tsMs,
                effectiveDistanceM=float(payload.effectiveFromLength * pool),
                timeline=runtime.timeline,
                profile=runtime.profile,
            )
        )
    return tuple(periods)


def _target_distance(
    timestamp_ms: int,
    periods: Sequence[_TargetPeriod],
    stops: Sequence[TimeInterval],
    pauses: Sequence[TimeInterval],
) -> tuple[float, _TargetPeriod]:
    period = periods[0]
    for candidate in periods:
        if candidate.appliedAtMs <= timestamp_ms:
            period = candidate
        else:
            break
    anchor_active_sec = target_active_time_at_distance(
        period.timeline, period.effectiveDistanceM
    ).elapsedActiveSec
    delta_ms = _active_between(period.appliedAtMs, timestamp_ms, stops, pauses)
    target = ghost_distance_at_active_time(
        period.timeline,
        anchor_active_sec + delta_ms / 1000.0,
        clamp=True,
    )
    return target.distanceM, period


def _phase_at_distance(timeline: PaceTimeline, distance_m: float) -> str:
    for interval in timeline.intervals:
        if interval.fromM - 1e-9 <= distance_m <= interval.toM + 1e-9:
            return interval.phaseType or "UNSPECIFIED"
    if not timeline.intervals:
        return "UNSPECIFIED"
    return timeline.intervals[-1].phaseType or "UNSPECIFIED"


def _observation_digest(observations: Sequence[_ResolvedObservation]) -> str:
    payload = [
        {
            "timestampMs": item.timestampMs,
            "estimatedDistanceM": item.estimatedDistanceM,
            "smoothedVelocityMps": item.smoothedVelocityMps,
            "phaseType": item.phaseType,
            "quality": item.quality,
            "source": item.source,
        }
        for item in observations
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _adherence(values: Sequence[float], tolerance_m: float) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if abs(value) <= tolerance_m) / len(values)


def _resolve_trusted_observations(
    *,
    observations: Sequence[SessionObservation],
    session_start_ms: int,
    horizon_ms: int,
    planned_distance_m: float | None,
    stops: Sequence[TimeInterval],
    pauses: Sequence[TimeInterval],
) -> tuple[tuple[_ResolvedObservation, ...], int, int]:
    previous_ts: int | None = None
    previous: _ResolvedObservation | None = None
    trusted: list[_ResolvedObservation] = []
    relevant_count = 0
    low_quality_count = 0

    for item in observations:
        if item.timestampMs < session_start_ms or item.timestampMs > horizon_ms:
            raise ObservationValidationError(
                f"observation timestamp {item.timestampMs} is outside session horizon "
                f"[{session_start_ms}, {horizon_ms}]"
            )
        if previous_ts is not None and item.timestampMs < previous_ts:
            raise ObservationValidationError("observation timestamps must be monotonic")
        previous_ts = item.timestampMs
        if item.estimatedDistanceM is not None and not math.isfinite(item.estimatedDistanceM):
            raise ObservationValidationError("observation distance must be finite")
        if item.smoothedVelocityMps is not None:
            if not math.isfinite(item.smoothedVelocityMps):
                raise ObservationValidationError("observation velocity must be finite")
            if item.smoothedVelocityMps < 0:
                raise ObservationValidationError("observation velocity must be non-negative")
        if item.estimatedDistanceM is None and item.smoothedVelocityMps is None:
            raise ObservationValidationError(
                "observation requires estimatedDistanceM or smoothedVelocityMps"
            )
        if item.plannedRest:
            continue

        relevant_count += 1
        allowed_quality = item.quality in {"HIGH", "MEDIUM"}
        if not allowed_quality:
            low_quality_count += 1
        if not item.trusted or not allowed_quality:
            continue

        distance = item.estimatedDistanceM
        if distance is None:
            velocity = item.smoothedVelocityMps
            assert velocity is not None
            if previous is None:
                if item.timestampMs != session_start_ms:
                    raise ObservationValidationError(
                        "velocity-only observations must start at sessionStartMs or follow a "
                        "trusted position anchor"
                    )
                distance = 0.0
            else:
                wall_dt_ms = item.timestampMs - previous.timestampMs
                if wall_dt_ms <= 0:
                    raise ObservationValidationError(
                        "velocity-only observations require strictly increasing timestamps"
                    )
                active_dt_ms = _active_between(
                    previous.timestampMs,
                    item.timestampMs,
                    stops,
                    pauses,
                )
                previous_velocity = previous.smoothedVelocityMps
                interval_velocity = (
                    (previous_velocity + velocity) / 2.0
                    if previous_velocity is not None
                    else velocity
                )
                distance = previous.estimatedDistanceM + interval_velocity * active_dt_ms / 1000.0

        if distance < -1e-6:
            raise ObservationValidationError("observation distance must be non-negative")
        if planned_distance_m is not None and distance > planned_distance_m + 1e-6:
            raise ObservationValidationError("observation distance exceeds workout bounds")
        if previous is not None and distance < previous.estimatedDistanceM - 1e-6:
            raise ObservationValidationError("trusted observation distance must be non-decreasing")

        resolved = _ResolvedObservation(
            timestampMs=item.timestampMs,
            estimatedDistanceM=max(0.0, distance),
            smoothedVelocityMps=item.smoothedVelocityMps,
            phaseType=item.phaseType,
            quality=item.quality,
            source=item.source,
        )
        trusted.append(resolved)
        previous = resolved

    return tuple(trusted), relevant_count, low_quality_count


def build_continuous_curve_analysis(
    *,
    replay_state: HistoricalSessionState,
    events: Sequence[EventEnvelope],
    pace_profile: ApprovedPaceProfileVersion | None,
    compiled_timeline: PaceTimeline | None,
    observations: Sequence[SessionObservation],
    report_context: ReportBuildContext,
    planned_distance_m: float | None,
) -> ContinuousCurveAnalysis:
    periods = _target_periods(
        state=replay_state,
        events=events,
        pace_profile=pace_profile,
        compiled_timeline=compiled_timeline,
        context=report_context,
    )
    if not periods:
        return ContinuousCurveAnalysis(
            available=False,
            status=MetricStatus.MISSING_TARGET,
            reason="MISSING_COMPILED_TARGET_TIMELINE",
            curveCoverageRatio=0.0,
            observationCount=0,
        )
    if replay_state.startedAtMs is None:
        return ContinuousCurveAnalysis(
            available=False,
            status=MetricStatus.NOT_APPLICABLE,
            reason="SESSION_NOT_STARTED",
            curveCoverageRatio=0.0,
            observationCount=0,
        )

    horizon = replay_state.endedAtMs or replay_state.lastEventTimestampMs
    stops = stop_pause_intervals(replay_state, horizon)
    pauses = lifecycle_pause_intervals(events, horizon)
    trusted, relevant_count, low_quality_count = _resolve_trusted_observations(
        observations=observations,
        session_start_ms=replay_state.startedAtMs,
        horizon_ms=horizon,
        planned_distance_m=planned_distance_m,
        stops=stops,
        pauses=pauses,
    )
    if planned_distance_m and trusted:
        distance_span = max(0.0, trusted[-1].estimatedDistanceM - trusted[0].estimatedDistanceM)
        coverage = min(1.0, distance_span / planned_distance_m)
    else:
        coverage = 0.0
    low_quality_ratio = low_quality_count / relevant_count if relevant_count else 0.0
    target_ref = (
        f"{pace_profile.profileId}:{pace_profile.profileVersion}"
        if pace_profile is not None
        else None
    )
    if low_quality_ratio > report_context.maximumLowQualityObservationRatio:
        return ContinuousCurveAnalysis(
            available=False,
            status=MetricStatus.LOW_QUALITY,
            reason="LOW_QUALITY_OBSERVATION_COVERAGE",
            targetContinuousCurveRef=target_ref,
            curveCoverageRatio=coverage,
            observationCount=len(trusted),
            curveRepresentation=replay_state.selectedCurveRepresentation,
            curveCompilerVersion=replay_state.selectedCurveCompilerVersion,
        )
    if (
        len(trusted) < report_context.minimumTrustedCurveObservations
        or coverage < report_context.minimumCurveCoverageRatio
    ):
        reason = (
            "INSUFFICIENT_TRUSTED_OBSERVATIONS"
            if len(trusted) < report_context.minimumTrustedCurveObservations
            else "INSUFFICIENT_CURVE_COVERAGE"
        )
        status = MetricStatus.LOW_QUALITY if relevant_count else MetricStatus.INSUFFICIENT_DATA
        return ContinuousCurveAnalysis(
            available=False,
            status=status,
            reason=reason,
            targetContinuousCurveRef=target_ref,
            curveCoverageRatio=coverage,
            observationCount=len(trusted),
            curveRepresentation=replay_state.selectedCurveRepresentation,
            curveCompilerVersion=replay_state.selectedCurveCompilerVersion,
            curveReconciliationErrorSec=(
                pace_profile.curveValidationSummary.totalReconciliationErrorSec
                if isinstance(pace_profile, ApprovedContinuousPaceProfile)
                and pace_profile.curveValidationSummary is not None
                else None
            ),
        )

    deviations: list[float] = []
    by_phase: dict[str, list[float]] = {}
    for item in trusted:
        target_distance, period = _target_distance(item.timestampMs, periods, stops, pauses)
        deviation = item.estimatedDistanceM - target_distance
        deviations.append(deviation)
        phase = item.phaseType or _phase_at_distance(period.timeline, target_distance)
        by_phase.setdefault(phase, []).append(deviation)

    phase_outputs: list[PhaseCurveDeviation] = []
    for phase in sorted(by_phase):
        values = by_phase[phase]
        phase_outputs.append(
            PhaseCurveDeviation(
                phaseType=phase,
                status=MetricStatus.AVAILABLE,
                observationCount=len(values),
                coverageRatio=len(values) / len(deviations),
                meanDistanceDeviationM=mean(values),
                meanAbsoluteDistanceDeviationM=mean([abs(value) for value in values]),
                rmsDistanceDeviationM=rms(values),
            )
        )

    def category_values(token: str) -> list[float]:
        return [
            value
            for phase, values in by_phase.items()
            if token in phase.upper()
            for value in values
        ]

    surface = [
        value
        for phase, values in by_phase.items()
        if not any(token in phase.upper() for token in ("START", "TURN", "FINISH", "UNDERWATER"))
        for value in values
    ]
    reconciliation_error = None
    if isinstance(pace_profile, ApprovedContinuousPaceProfile):
        summary = pace_profile.curveValidationSummary
        reconciliation_error = summary.totalReconciliationErrorSec if summary is not None else None
    return ContinuousCurveAnalysis(
        available=True,
        status=MetricStatus.AVAILABLE,
        targetContinuousCurveRef=target_ref,
        actualSmoothedCurveRef=f"sha256:{_observation_digest(trusted)}",
        curveDeviationMean=mean(deviations),
        curveDeviationMeanAbsolute=mean([abs(value) for value in deviations]),
        curveDeviationRms=rms(deviations),
        curveDeviationByPhase=tuple(phase_outputs),
        peakPositiveDeviation=max(deviations),
        peakNegativeDeviation=min(deviations),
        startCurveAdherence=_adherence(
            category_values("START"), report_context.curveAdherenceToleranceM
        ),
        turnCurveAdherence=_adherence(
            category_values("TURN"), report_context.curveAdherenceToleranceM
        ),
        surfaceCurveAdherence=_adherence(surface, report_context.curveAdherenceToleranceM),
        finishCurveAdherence=_adherence(
            category_values("FINISH"), report_context.curveAdherenceToleranceM
        ),
        curveCoverageRatio=coverage,
        observationCount=len(trusted),
        curveRepresentation=replay_state.selectedCurveRepresentation,
        curveCompilerVersion=replay_state.selectedCurveCompilerVersion,
        curveReconciliationErrorSec=reconciliation_error,
    )
