from __future__ import annotations

from analytics.sensors import build_sensor_analysis
from analytics.types import ReportBuildContext, SensorObservation
from tests.unit._analytics_helpers import case


def test_sensor_analysis_is_optional_and_advisory() -> None:
    _wk, _profile, _events, state, _timeline = case()
    empty = build_sensor_analysis(
        replay_state=state, samples=(), report_context=ReportBuildContext()
    )
    assert empty.heartRate.averageHeartRateBpm is None
    samples = (
        SensorObservation(timestampMs=0, heartRateBpm=120, paceSecPer100M=80),
        SensorObservation(timestampMs=40_000, heartRateBpm=140, paceSecPer100M=82),
        SensorObservation(timestampMs=80_000, heartRateBpm=160, paceSecPer100M=84),
    )
    result = build_sensor_analysis(
        replay_state=state, samples=samples, report_context=ReportBuildContext()
    )
    assert result.heartRate.available is True
    assert result.heartRate.averageHeartRateBpm == 140
