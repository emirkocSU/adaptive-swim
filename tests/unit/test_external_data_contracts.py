"""External-data plan-level contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.enums import ExternalDataDomain, ExternalDataRole, VerificationStatus
from contracts.external_data import (
    DataSourceRegistryEntry,
    ExternalRecordProvenance,
    NormalizedSwimmingRecord,
    merge_normalized_records,
    require_data_domain,
)


def _provenance() -> ExternalRecordProvenance:
    return ExternalRecordProvenance(sourceId="s1", sourceRecordId="r1")


def _record(domain: ExternalDataDomain, *, synthetic: bool = False) -> NormalizedSwimmingRecord:
    return NormalizedSwimmingRecord(
        source_id="s1",
        source_record_id="r1",
        athlete_pseudonym="A#001",
        session_or_race_id="race-1",
        data_domain=domain,
        synthetic=synthetic,
        provenance_ref=_provenance(),
    )


def test_data_domain_is_required_to_build_a_record() -> None:
    with pytest.raises(ValidationError):
        NormalizedSwimmingRecord(  # type: ignore[call-arg]
            source_id="s1",
            source_record_id="r1",
            athlete_pseudonym="A#001",
            session_or_race_id="race-1",
            provenance_ref=_provenance(),
        )


def test_merge_requires_data_domain() -> None:
    class _NoDomain:
        data_domain = None

    with pytest.raises(ValueError, match="data_domain"):
        require_data_domain([_NoDomain()])  # type: ignore[list-item]


def test_merge_ok_when_all_have_domain() -> None:
    race = [_record(ExternalDataDomain.ELITE_RACE)]
    training = [_record(ExternalDataDomain.TRAINING_EXPORT)]
    merged = merge_normalized_records(race, training)
    assert len(merged) == 2


def test_no_production_eligibility_flag_on_external_records() -> None:
    for model in (NormalizedSwimmingRecord, DataSourceRegistryEntry):
        fields = {name.lower() for name in model.model_fields}
        for forbidden in ("productioneligible", "production_eligibility", "productioneligibility"):
            assert forbidden not in fields, f"{model.__name__} exposes {forbidden}"


def test_synthetic_records_carry_flag_and_provenance() -> None:
    rec = _record(ExternalDataDomain.SYNTHETIC_SIMULATION, synthetic=True)
    assert rec.synthetic is True
    assert rec.provenance_ref is not None
    # provenance is structurally required for every record.
    assert NormalizedSwimmingRecord.model_fields["provenance_ref"].is_required()


def test_external_data_domain_enum_values() -> None:
    assert {d.value for d in ExternalDataDomain} == {
        "ELITE_RACE",
        "TRAINING_EXPORT",
        "WEARABLE_SENSOR",
        "ADAPTIVE_SWIM_SESSION",
        "SYNTHETIC_SIMULATION",
    }


def test_ambiguous_license_defaults_to_tbd() -> None:
    entry = DataSourceRegistryEntry(
        sourceId="s1",
        sourceName="Example",
        ownerOrPublisher="Org",
        sourceType="race_results",
        accessMethod="manual",
        intendedRole=ExternalDataRole.L1_RACE_PACING_PRIOR,
    )
    assert entry.licenseStatus is VerificationStatus.TBD_VERIFICATION_REQUIRED
    assert entry.commercialUseStatus is VerificationStatus.TBD_VERIFICATION_REQUIRED


def test_swimcore_does_not_import_external_data() -> None:
    from pathlib import Path

    swimcore = Path(__file__).resolve().parents[2] / "src" / "swimcore"
    for py in swimcore.rglob("*.py"):
        assert "contracts.external_data" not in py.read_text(encoding="utf-8")
