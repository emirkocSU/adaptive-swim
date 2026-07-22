from __future__ import annotations

from simulator.harness import SimulationResult


def test_missing_sensor_data_is_not_fabricated(
    normal_report_result: SimulationResult,
) -> None:
    sensor = normal_report_result.sessionReport.sensorAnalysis
    assert sensor.heartRate.available is False
    assert sensor.heartRate.averageHeartRateBpm is None
    assert sensor.stroke.available is False
    assert sensor.stroke.averageStrokeRateCyclesPerMin is None


def test_dataset_evidence_is_only_copied_from_profile_provenance(
    normal_report_result: SimulationResult,
) -> None:
    provenance = normal_report_result.sessionReport.provenance
    assert provenance.datasetEvidenceAssetIds
    assert provenance.continuousCurveGroundTruth is False
    assert (
        "SYNTHETIC_NOT_PERFORMANCE_EVIDENCE"
        in normal_report_result.sessionReport.dataQuality.warningCodes
    )
