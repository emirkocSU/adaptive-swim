"""Optional advisory heart-rate and stroke summaries."""

from __future__ import annotations

import math
from collections.abc import Sequence

from analytics._math import least_squares_slope, mean, pearson
from analytics.types import ReportBuildContext, SensorObservation
from contracts.session_report import (
    HeartRateAnalysis,
    MetricStatus,
    SensorAnalysis,
    StrokeAnalysis,
)
from swimcore.replay.state import HistoricalSessionState


def _coverage(timestamps: Sequence[int], state: HistoricalSessionState) -> float:
    if len(timestamps) < 2 or state.wallDurationMs <= 0:
        return 0.0
    return min(1.0, max(0, timestamps[-1] - timestamps[0]) / state.wallDurationMs)


def build_sensor_analysis(
    *,
    replay_state: HistoricalSessionState,
    samples: Sequence[SensorObservation],
    report_context: ReportBuildContext,
) -> SensorAnalysis:
    trusted = [
        sample for sample in samples if sample.trusted and sample.quality in {"HIGH", "MEDIUM"}
    ]
    trusted.sort(key=lambda item: item.timestampMs)

    hr_samples = [
        sample
        for sample in trusted
        if sample.heartRateBpm is not None
        and math.isfinite(sample.heartRateBpm)
        and sample.heartRateBpm > 0
    ]
    hr_values = [
        float(sample.heartRateBpm) for sample in hr_samples if sample.heartRateBpm is not None
    ]
    hr_coverage = _coverage([sample.timestampMs for sample in hr_samples], replay_state)
    if hr_values:
        trend = None
        if len(hr_samples) >= report_context.minimumSensorSamplesForTrend:
            origin = hr_samples[0].timestampMs
            xs = [(sample.timestampMs - origin) / 60_000.0 for sample in hr_samples]
            trend = least_squares_slope(xs, hr_values)
        paired = [
            (float(sample.heartRateBpm), float(sample.paceSecPer100M))
            for sample in hr_samples
            if sample.heartRateBpm is not None
            and sample.paceSecPer100M is not None
            and math.isfinite(sample.paceSecPer100M)
            and sample.paceSecPer100M > 0
        ]
        relationship = (
            pearson([item[0] for item in paired], [item[1] for item in paired])
            if len(paired) >= 3
            else None
        )
        heart_rate = HeartRateAnalysis(
            available=True,
            status=MetricStatus.AVAILABLE,
            sampleCount=len(hr_values),
            averageHeartRateBpm=mean(hr_values),
            minimumHeartRateBpm=min(hr_values),
            maximumHeartRateBpm=max(hr_values),
            heartRateTrendBpmPerMinute=trend,
            heartRatePaceRelationship=relationship,
            coverageRatio=hr_coverage,
            qualityFlags=(),
        )
    else:
        heart_rate = HeartRateAnalysis(
            available=False,
            status=MetricStatus.INSUFFICIENT_DATA,
            sampleCount=0,
            coverageRatio=0.0,
            qualityFlags=("NO_TRUSTED_HEART_RATE",),
        )

    stroke_samples = [
        sample
        for sample in trusted
        if any(
            value is not None
            for value in (
                sample.strokeRateCyclesPerMin,
                sample.strokeLengthMPerCycle,
                sample.strokeIndex,
                sample.strokeCount,
            )
        )
    ]
    definitions = {
        sample.strokeDefinition for sample in stroke_samples if sample.strokeDefinition is not None
    }
    inconsistent_definition = len(definitions) > 1
    stroke_coverage = _coverage([sample.timestampMs for sample in stroke_samples], replay_state)
    if stroke_samples and not inconsistent_definition:
        rates = [
            float(sample.strokeRateCyclesPerMin)
            for sample in stroke_samples
            if sample.strokeRateCyclesPerMin is not None
            and math.isfinite(sample.strokeRateCyclesPerMin)
            and sample.strokeRateCyclesPerMin >= 0
        ]
        lengths = [
            float(sample.strokeLengthMPerCycle)
            for sample in stroke_samples
            if sample.strokeLengthMPerCycle is not None
            and math.isfinite(sample.strokeLengthMPerCycle)
            and sample.strokeLengthMPerCycle >= 0
        ]
        indices = [
            float(sample.strokeIndex)
            for sample in stroke_samples
            if sample.strokeIndex is not None
            and math.isfinite(sample.strokeIndex)
            and sample.strokeIndex >= 0
        ]
        counts = [
            float(sample.strokeCount)
            for sample in stroke_samples
            if sample.strokeCount is not None
            and math.isfinite(sample.strokeCount)
            and sample.strokeCount >= 0
        ]
        rate_trend = None
        rate_samples = [
            sample
            for sample in stroke_samples
            if sample.strokeRateCyclesPerMin is not None
            and math.isfinite(sample.strokeRateCyclesPerMin)
        ]
        if len(rate_samples) >= report_context.minimumSensorSamplesForTrend:
            origin = rate_samples[0].timestampMs
            rate_trend = least_squares_slope(
                [(sample.timestampMs - origin) / 60_000.0 for sample in rate_samples],
                [
                    float(sample.strokeRateCyclesPerMin)
                    for sample in rate_samples
                    if sample.strokeRateCyclesPerMin is not None
                ],
            )
        stroke = StrokeAnalysis(
            available=True,
            status=MetricStatus.AVAILABLE,
            sampleCount=len(stroke_samples),
            averageStrokeRateCyclesPerMin=mean(rates) if rates else None,
            strokeRateTrend=rate_trend,
            averageStrokeLengthMPerCycle=mean(lengths) if lengths else None,
            averageStrokeIndex=mean(indices) if indices else None,
            strokeCountTotal=sum(counts) if counts else None,
            coverageRatio=stroke_coverage,
            qualityFlags=(),
        )
    else:
        stroke = StrokeAnalysis(
            available=False,
            status=(
                MetricStatus.LOW_QUALITY
                if inconsistent_definition
                else MetricStatus.INSUFFICIENT_DATA
            ),
            sampleCount=len(stroke_samples),
            coverageRatio=stroke_coverage,
            qualityFlags=(
                ("MIXED_STROKE_DEFINITIONS",)
                if inconsistent_definition
                else ("NO_TRUSTED_STROKE_DATA",)
            ),
        )
    return SensorAnalysis(heartRate=heart_rate, stroke=stroke)
