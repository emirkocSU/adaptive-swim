"""Metric-availability and report-level quality synthesis."""

from __future__ import annotations

from contracts.session_report import (
    ContinuousCurveAnalysis,
    DistanceSummary,
    MetricAvailability,
    ReportDataQuality,
    SensorAnalysis,
    SplitAnalysis,
    TimingSummary,
)


def build_report_data_quality(
    *,
    event_stream_complete: bool,
    replay_valid: bool,
    timing: TimingSummary,
    distance: DistanceSummary,
    splits: SplitAnalysis,
    curve: ContinuousCurveAnalysis,
    sensors: SensorAnalysis,
    target_profile_available: bool,
    warning_codes: tuple[str, ...],
) -> ReportDataQuality:
    sensor_coverage = max(
        sensors.heartRate.coverageRatio,
        sensors.stroke.coverageRatio,
    )
    availability = (
        MetricAvailability(metric="timingSummary", status=timing.status),
        MetricAvailability(metric="officialDistanceSummary", status=distance.status),
        MetricAvailability(metric="officialSplitAnalysis", status=splits.status),
        MetricAvailability(
            metric="continuousCurveAnalysis",
            status=curve.status,
            reason=curve.reason,
        ),
        MetricAvailability(metric="heartRateAnalysis", status=sensors.heartRate.status),
        MetricAvailability(metric="strokeAnalysis", status=sensors.stroke.status),
    )
    return ReportDataQuality(
        eventStreamComplete=event_stream_complete,
        replayValid=replay_valid,
        officialDistanceComplete=not distance.partial,
        targetProfileAvailable=target_profile_available,
        continuousObservationCoverage=curve.curveCoverageRatio,
        sensorCoverage=sensor_coverage,
        excludedSplitCount=splits.aggregate.excludedSplitCount,
        warningCodes=tuple(dict.fromkeys(warning_codes)),
        metricAvailability=availability,
    )
