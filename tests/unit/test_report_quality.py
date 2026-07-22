from __future__ import annotations

from tests.unit._analytics_helpers import report


def test_metric_status_is_separate_from_numeric_value() -> None:
    result = report()
    assert result.sensorAnalysis.heartRate.status.value == "INSUFFICIENT_DATA"
    assert result.sensorAnalysis.heartRate.averageHeartRateBpm is None
    assert result.dataQuality.eventStreamComplete is True
