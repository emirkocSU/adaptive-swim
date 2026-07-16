"""External data — PLAN-LEVEL contracts only.

This module must NEVER be imported by ``swimcore`` (import-linter forbidden rule). It is
consumed only by documentation and (later) a separate research epic — never by the runtime.

Rules enforced by tests:
- External data cannot earn production eligibility (no such field exists here).
- Synthetic data is not performance evidence; synthetic records carry ``synthetic=true``
  and provenance.
- Race / training / adaptive-swim records cannot be merged without ``data_domain``.
- Missingness is preserved (Optional fields; no fake filling).
- Ambiguous license/access is marked ``TBD_VERIFICATION_REQUIRED``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import model_validator

from contracts._base import NonEmptyStr, StrictModel
from contracts.enums import (
    ExternalDataDomain,
    ExternalDataRole,
    VerificationStatus,
)


class DataSourceRegistryEntry(StrictModel):
    sourceId: str
    sourceName: str
    ownerOrPublisher: str
    sourceType: str
    accessMethod: str
    sourceUrlOrReference: str | None = None
    licenseStatus: VerificationStatus = VerificationStatus.TBD_VERIFICATION_REQUIRED
    commercialUseStatus: VerificationStatus = VerificationStatus.TBD_VERIFICATION_REQUIRED
    redistributionStatus: VerificationStatus = VerificationStatus.TBD_VERIFICATION_REQUIRED
    consentRequired: bool = True
    dataAvailabilityStatus: VerificationStatus = VerificationStatus.TBD_VERIFICATION_REQUIRED
    availableFields: list[str] = []
    granularity: str | None = None
    intendedRole: ExternalDataRole
    prohibitedUses: list[str] = []
    provenanceMethod: str | None = None
    retrievalDate: str | None = None
    contentHashOrVersion: str | None = None
    notes: str | None = None


class ExternalRecordProvenance(StrictModel):
    sourceId: NonEmptyStr
    sourceRecordId: NonEmptyStr
    retrievalDate: str | None = None
    contentHashOrVersion: str | None = None
    transformationRef: str | None = None
    consentRef: str | None = None


class NormalizedSwimmingRecord(StrictModel):
    source_id: str
    source_record_id: str
    athlete_pseudonym: str
    session_or_race_id: str
    #: REQUIRED. Records from different domains cannot be merged without this.
    data_domain: ExternalDataDomain
    stroke: str | None = None
    pool_length_m: int | None = None
    event_or_set_distance_m: int | None = None
    length_or_split_index: int | None = None
    cumulative_time_sec: float | None = None
    length_or_split_time_sec: float | None = None
    target_pace_sec_per_100m: float | None = None
    rest_before_sec: float | None = None
    stroke_rate: float | None = None
    stroke_count: int | None = None
    swolf: float | None = None
    heart_rate: float | None = None
    heart_rate_trend: float | None = None
    sensor_quality: float | None = None
    incident_like_flag: bool | None = None
    quality_flag: str | None = None
    synthetic: bool = False
    provenance_ref: ExternalRecordProvenance

    @model_validator(mode="after")
    def _synthetic_domain_consistency(self) -> NormalizedSwimmingRecord:
        # Two-way rule: data_domain == SYNTHETIC_SIMULATION  <=>  synthetic == True.
        is_synth_domain = self.data_domain is ExternalDataDomain.SYNTHETIC_SIMULATION
        if is_synth_domain and not self.synthetic:
            raise ValueError("SYNTHETIC_SIMULATION domain requires synthetic=True")
        if self.synthetic and not is_synth_domain:
            raise ValueError("synthetic=True requires data_domain == SYNTHETIC_SIMULATION")
        # Synthetic records must carry non-empty provenance identifiers.
        if self.synthetic and (
            not self.provenance_ref.sourceId or not self.provenance_ref.sourceRecordId
        ):
            raise ValueError("synthetic records must carry non-empty provenance")
        return self


def require_data_domain(records: Iterable[NormalizedSwimmingRecord]) -> None:
    """Raise if any record is missing a ``data_domain``.

    Guards the invariant that race/training/adaptive-swim records cannot be blended
    without an explicit domain. (Typed records always have one; this also rejects raw
    dicts that were coerced without it.)
    """
    for rec in records:
        if getattr(rec, "data_domain", None) is None:
            raise ValueError("cannot merge external records without data_domain")


def merge_normalized_records(
    *groups: Sequence[NormalizedSwimmingRecord],
) -> list[NormalizedSwimmingRecord]:
    """Merge normalized records only after the ``data_domain`` guard passes."""
    merged: list[NormalizedSwimmingRecord] = []
    for group in groups:
        require_data_domain(group)
        merged.extend(group)
    return merged
