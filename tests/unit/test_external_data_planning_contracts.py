"""External-data planning-model contract extensions (§15)."""

from __future__ import annotations

from contracts.enums import ExternalDataDomain, ExternalDataRole, VerificationStatus
from contracts.external_data import (
    DataSourceRegistryEntry,
    ExternalRecordProvenance,
    NormalizedSwimmingRecord,
)


def _entry(**over: object) -> DataSourceRegistryEntry:
    base: dict = {
        "sourceId": "s1",
        "sourceName": "Open Race DB",
        "ownerOrPublisher": "Public",
        "sourceType": "csv",
        "accessMethod": "download",
        "intendedRole": ExternalDataRole.L1_RACE_PACING_PRIOR,
    }
    base.update(over)
    return DataSourceRegistryEntry(**base)


def _record(**over: object) -> NormalizedSwimmingRecord:
    base: dict = {
        "source_id": "s1",
        "source_record_id": "r1",
        "athlete_pseudonym": "a1",
        "session_or_race_id": "race1",
        "data_domain": ExternalDataDomain.ELITE_RACE,
        "provenance_ref": ExternalRecordProvenance(sourceId="s1", sourceRecordId="r1"),
    }
    base.update(over)
    return NormalizedSwimmingRecord(**base)


def test_unverified_license_not_live_model_eligible() -> None:
    e = _entry(licenseVerified=False)
    assert not e.is_planning_model_eligible


def test_verified_license_is_planning_model_eligible() -> None:
    e = _entry(
        licenseVerified=True,
        licenseStatus=VerificationStatus.ALLOWED,
        license="CC-BY-4.0",
        allowedUsage=["training", "commercial"],
    )
    assert e.is_planning_model_eligible


def test_start_mode_and_pool_are_preserved_in_normalized_record() -> None:
    r = _record(pool_length_m=50, start_mode="DIVE_START")
    assert r.pool_length_m == 50
    assert r.start_mode == "DIVE_START"


def test_split_ratio_missingness_is_preserved() -> None:
    r = _record()  # split_ratio not supplied
    assert r.split_ratio is None  # no fake filling


def test_synthetic_rules_still_hold() -> None:
    # synthetic=True requires SYNTHETIC_SIMULATION domain (unchanged rule)
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _record(synthetic=True)


def test_planning_features_optional_default_none() -> None:
    r = _record()
    assert r.reaction_time_sec is None
    assert r.start_15m_time_sec is None
    assert r.percent_of_personal_best is None
