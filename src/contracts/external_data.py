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
    # --- planning-model provenance (§15). Explicit license verification is mandatory before
    #     a source may feed a production planning model. ---
    sourceUrl: str | None = None
    license: str | None = None
    licenseVerified: bool = False
    retrievedAt: str | None = None
    transformationVersion: str | None = None
    dataQualityLevel: str | None = None
    allowedUsage: list[str] = []
    # --- continuous-curve capability flags (ADR-038). Optional; describe whether a source
    #     can supply continuous position/time and phase labels for curve extraction. ---
    continuousPositionTimeAvailable: bool | None = None
    phaseLabelsAvailable: bool | None = None
    samplingFrequencyHz: float | None = None
    trackingMethod: str | None = None
    velocitySmoothingMethod: str | None = None
    curveExtractionVersion: str | None = None
    curveConfidenceAvailable: bool | None = None

    @property
    def is_planning_model_eligible(self) -> bool:
        """A source is planning-model eligible only when its license is explicitly verified
        and not left as TBD_VERIFICATION_REQUIRED."""
        return (
            self.licenseVerified
            and self.licenseStatus is not VerificationStatus.TBD_VERIFICATION_REQUIRED
        )


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
    # --- planning-model features (§15). All optional; missingness is preserved (no fake
    #     filling). These map the newest document's normalized-record vocabulary. ---
    total_time_sec: float | None = None
    split_time_sec: float | None = None
    split_ratio: float | None = None
    distance_m: float | None = None
    age_years: int | None = None
    age_group: str | None = None
    sex_category: str | None = None
    athlete_level: str | None = None
    start_mode: str | None = None
    turn_count: int | None = None
    reaction_time_sec: float | None = None
    start_15m_time_sec: float | None = None
    final_section_time_sec: float | None = None
    pace_profile_type: str | None = None
    distance_per_stroke: float | None = None
    heart_rate_zone: str | None = None
    recovery_heart_rate: float | None = None
    workout_goal: str | None = None
    effort_level: float | None = None
    race_or_training_context: str | None = None
    percent_of_personal_best: float | None = None
    biomechanical_features: dict[str, float] | None = None
    physiological_features: dict[str, float] | None = None
    # --- continuous pace-curve features (ADR-038). All optional; missingness preserved, no
    #     fake filling. Split-only data must NOT be presented as continuous ground truth. ---
    timestamp_ms: int | None = None
    raw_velocity_mps: float | None = None
    smoothed_velocity_mps: float | None = None
    target_velocity_envelope_mps: float | None = None
    phase_type: str | None = None
    phase_start_m: float | None = None
    phase_end_m: float | None = None
    phase_duration_sec: float | None = None
    event_distance_m: float | None = None
    turn_index: int | None = None
    distance_to_wall_m: float | None = None
    split_speed_mps: float | None = None
    free_swimming_distance_m: float | None = None
    free_swimming_time_sec: float | None = None
    clean_swimming_speed_mps: float | None = None
    stroke_length_m_per_cycle: float | None = None
    stroke_rate_cycles_per_min: float | None = None
    stroke_index: float | None = None
    sampling_frequency_hz: float | None = None
    tracking_method: str | None = None
    curve_smoothing_method: str | None = None
    curve_extraction_version: str | None = None
    velocity_extraction_method: str | None = None
    curve_integral_time_sec: float | None = None
    curve_reconciliation_error_sec: float | None = None
    curve_confidence: float | None = None
    velocity_confidence: float | None = None
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
