"""External-data continuous fields + continuous report context tests (Commit 8 §37)."""

from __future__ import annotations

import pytest

from contracts.analytics import ContinuousCurveReportContext, PaceProfileReportContext
from contracts.enums import ExternalDataDomain, ExternalDataRole
from contracts.external_data import (
    DataSourceRegistryEntry,
    ExternalRecordProvenance,
    NormalizedSwimmingRecord,
)


def _record(**overrides: object) -> NormalizedSwimmingRecord:
    base: dict[str, object] = {
        "source_id": "src",
        "source_record_id": "r1",
        "athlete_pseudonym": "athlete",
        "session_or_race_id": "s1",
        "data_domain": ExternalDataDomain.SYNTHETIC_SIMULATION,
        "synthetic": True,
        "provenance_ref": ExternalRecordProvenance(sourceId="src", sourceRecordId="r1"),
    }
    base.update(overrides)
    return NormalizedSwimmingRecord(**base)  # type: ignore[arg-type]


def test_continuous_fields_optional_and_default_none() -> None:
    r = _record()
    assert r.raw_velocity_mps is None
    assert r.phase_type is None
    assert r.curve_confidence is None
    assert r.sampling_frequency_hz is None


def test_continuous_fields_accepted_when_present() -> None:
    r = _record(
        timestamp_ms=1000,
        raw_velocity_mps=1.4,
        smoothed_velocity_mps=1.38,
        phase_type="SURFACE_SWIM",
        distance_to_wall_m=5.0,
        stroke_index=2.7,
        curve_reconciliation_error_sec=0.0,
        tracking_method="video",
    )
    assert r.raw_velocity_mps == 1.4
    assert r.phase_type == "SURFACE_SWIM"
    assert r.tracking_method == "video"


def test_missingness_is_preserved_no_fake_fill() -> None:
    # a split-only record leaves all continuous velocity fields None (not zero-filled)
    r = _record(length_or_split_time_sec=20.0)
    assert r.raw_velocity_mps is None
    assert r.smoothed_velocity_mps is None
    assert r.target_velocity_envelope_mps is None


def test_registry_capability_flags_optional() -> None:
    entry = DataSourceRegistryEntry(
        sourceId="s",
        sourceName="Src",
        ownerOrPublisher="owner",
        sourceType="research",
        accessMethod="download",
        intendedRole=ExternalDataRole.L1_RACE_PACING_PRIOR,
    )
    assert entry.continuousPositionTimeAvailable is None
    assert entry.phaseLabelsAvailable is None


def test_registry_capability_flags_settable() -> None:
    entry = DataSourceRegistryEntry(
        sourceId="s",
        sourceName="Src",
        ownerOrPublisher="owner",
        sourceType="research",
        accessMethod="download",
        intendedRole=ExternalDataRole.L1_RACE_PACING_PRIOR,
        continuousPositionTimeAvailable=True,
        phaseLabelsAvailable=False,
        samplingFrequencyHz=100.0,
        trackingMethod="video",
        curveConfidenceAvailable=True,
    )
    assert entry.continuousPositionTimeAvailable is True
    assert entry.samplingFrequencyHz == 100.0


def test_synthetic_domain_still_enforced() -> None:
    with pytest.raises(ValueError, match="SYNTHETIC_SIMULATION"):
        _record(data_domain=ExternalDataDomain.SYNTHETIC_SIMULATION, synthetic=False)


# ---------------------------------------------------------------- report context
def test_continuous_report_context_optional_on_profile_context() -> None:
    ctx = PaceProfileReportContext()
    assert ctx.continuousCurve is None


def test_continuous_report_context_fields() -> None:
    cc = ContinuousCurveReportContext(
        targetContinuousCurveRef="curve-1",
        curveDeviationMean=0.05,
        curveDeviationByPhase={"SURFACE_SWIM": 0.03},
        peakPositiveDeviation=0.2,
        startCurveAdherence=0.9,
        curveRepresentation="PCHIP",
        curveCompilerVersion="continuous-1.1.0",
        curveReconciliationErrorSec=0.0,
    )
    ctx = PaceProfileReportContext(continuousCurve=cc)
    assert ctx.continuousCurve is not None
    assert ctx.continuousCurve.curveRepresentation == "PCHIP"
    assert ctx.continuousCurve.curveDeviationByPhase == {"SURFACE_SWIM": 0.03}


def test_report_context_extra_fields_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ContinuousCurveReportContext(surprise=1)  # type: ignore[call-arg]


def test_old_report_context_still_valid_without_continuous() -> None:
    ctx = PaceProfileReportContext(
        poolLengthM=25,
        paceProfileId="p1",
        targetTotalTimeSec=80.0,
    )
    assert ctx.continuousCurve is None
    assert ctx.paceProfileId == "p1"
