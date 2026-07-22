"""Dataset asset manifest contracts (ADR-039, real-bundle correction).

The checked-in catalog describes the *real raw ZIP members and raw CSV headers*. Canonical
research names such as ``subject_uid``, ``session_uid`` and ``record_type`` are never
silently required from a source file that does not contain them. Instead each CSV member may
declare an explicit ``normalizedColumnMapping`` from raw source columns to canonical view
columns.

These contracts are metadata only. Raw CSV/ZIP files stay outside the repository and are
validated by :mod:`swimtools.validate_dataset_bundle`.

Hard rules:

- a license other than ``VERIFIED_ALLOWED`` cannot yield production eligibility;
- quarantined/file-level smoke-test data can only carry ``PIPELINE_SMOKE_TEST``;
- coarse race, training and processed sensor data cannot claim measured continuous velocity;
- file-level policy may be stricter than the containing multi-file bundle;
- normalized mappings name real raw columns and are validated before a view is built.

``swimcore`` MUST NOT import this module.
"""

from __future__ import annotations

from pydantic import model_validator

from contracts._base import NonEmptyStr, NonNegInt, PosInt, StrictModel
from contracts.enums import (
    DatasetDomain,
    DatasetEligibility,
    DatasetEvidenceLevel,
    DatasetGranularity,
    DatasetRole,
    LicenseEligibility,
    ModelTask,
)

_SHA256_HEX_LEN = 64


def _check_sha256(value: str, label: str) -> None:
    if len(value) != _SHA256_HEX_LEN or any(c not in "0123456789abcdef" for c in value.lower()):
        raise ValueError(f"{label} must be a 64-char lowercase hex SHA-256, got {value!r}")


def _check_eligibility_policy(
    *,
    label: str,
    roles: tuple[DatasetRole, ...],
    allowed_tasks: tuple[ModelTask, ...],
    license_eligibility: LicenseEligibility,
    eligibility: DatasetEligibility,
    production_training_eligible: bool,
) -> None:
    if (
        license_eligibility is not LicenseEligibility.VERIFIED_ALLOWED
        and eligibility is DatasetEligibility.PRODUCTION_ELIGIBLE
    ):
        raise ValueError(
            f"{label}: eligibility PRODUCTION_ELIGIBLE requires licenseEligibility "
            "VERIFIED_ALLOWED (license TBD/blocked/mixed cannot be production eligible)"
        )
    if eligibility is DatasetEligibility.PRODUCTION_ELIGIBLE and not production_training_eligible:
        raise ValueError(
            f"{label}: productionTrainingEligible=False cannot be overridden by "
            "eligibility PRODUCTION_ELIGIBLE"
        )
    if production_training_eligible and eligibility in (
        DatasetEligibility.QUARANTINED,
        DatasetEligibility.SMOKE_TEST_ONLY,
        DatasetEligibility.LICENSE_BLOCKED,
        DatasetEligibility.QUALITY_BLOCKED,
    ):
        raise ValueError(
            f"{label}: productionTrainingEligible is incompatible with {eligibility.value}"
        )

    if eligibility in (DatasetEligibility.QUARANTINED, DatasetEligibility.SMOKE_TEST_ONLY):
        if production_training_eligible:
            raise ValueError(f"{label}: quarantined data can never be production eligible")
        bad = [task for task in allowed_tasks if task is not ModelTask.PIPELINE_SMOKE_TEST]
        if bad:
            raise ValueError(
                f"{label}: quarantined / smoke-test-only data may only carry "
                f"PIPELINE_SMOKE_TEST, got {[task.value for task in bad]}"
            )
        if DatasetRole.PIPELINE_SMOKE_TEST_ONLY not in roles:
            raise ValueError(f"{label}: quarantined data must carry PIPELINE_SMOKE_TEST_ONLY")


class DatasetRestriction(StrictModel):
    """One machine-checkable restriction on how a dataset (or file) may be used."""

    code: NonEmptyStr
    description: NonEmptyStr


class DatasetValidationSummary(StrictModel):
    """Result summary of one streaming validation run (produced by the validator)."""

    assetId: NonEmptyStr
    bundleValid: bool
    validatedFileCount: NonNegInt
    rowCountMatches: bool
    columnCountMatches: bool
    hashesMatch: bool
    requiredColumnsPresent: bool
    warnings: tuple[str, ...] = ()
    blockingErrors: tuple[str, ...] = ()


class DatasetFilePolicy(StrictModel):
    """Eligibility and role policy for one member of a multi-file bundle."""

    roles: tuple[DatasetRole, ...]
    allowedModelTasks: tuple[ModelTask, ...]
    licenseEligibility: LicenseEligibility
    eligibility: DatasetEligibility
    productionTrainingEligible: bool = False
    continuousCurveGroundTruth: bool = False
    officialDistanceAuthority: bool = False
    restrictions: tuple[DatasetRestriction, ...] = ()

    @model_validator(mode="after")
    def _check_rules(self) -> DatasetFilePolicy:
        _check_eligibility_policy(
            label="file policy",
            roles=self.roles,
            allowed_tasks=self.allowedModelTasks,
            license_eligibility=self.licenseEligibility,
            eligibility=self.eligibility,
            production_training_eligible=self.productionTrainingEligible,
        )
        return self


class DatasetFileManifest(StrictModel):
    """Expected identity, raw shape and normalized-view mapping of one ZIP member."""

    fileName: NonEmptyStr
    #: Expected SHA-256. ``None`` is allowed only while a real local validation has not yet
    #: recorded it; the validator reports the measured hash as a warning.
    sha256: NonEmptyStr | None = None
    expectedRowCount: NonNegInt | None = None
    expectedColumnCount: PosInt | None = None
    #: These are *raw source header names*, never canonical names invented by the project.
    requiredColumns: tuple[NonEmptyStr, ...] = ()
    granularity: DatasetGranularity | None = None
    #: Real raw discriminator column (for example ``record_granularity``).
    granularityColumn: NonEmptyStr | None = None
    granularityRowCounts: dict[str, int] | None = None
    #: Raw source column -> canonical normalized-view column.
    normalizedColumnMapping: dict[NonEmptyStr, NonEmptyStr] = {}
    #: Optional structural value constraints checked while streaming the real CSV.
    allowedColumnValues: dict[NonEmptyStr, tuple[NonEmptyStr, ...]] = {}
    #: Raw grouping keys used by leakage-safe partitioning.
    groupingKeys: tuple[NonEmptyStr, ...] = ()
    forbiddenFeatureColumns: tuple[NonEmptyStr, ...] = ()
    #: File-level role/eligibility. Required for members whose policy differs from the bundle.
    policy: DatasetFilePolicy | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> DatasetFileManifest:
        if self.sha256 is not None:
            _check_sha256(self.sha256, f"file {self.fileName} sha256")

        required = set(self.requiredColumns)
        mapped_raw = set(self.normalizedColumnMapping)
        missing_mapping_sources = sorted(mapped_raw - required)
        if missing_mapping_sources:
            raise ValueError(
                f"file {self.fileName}: normalized mapping raw columns must also be raw "
                f"requiredColumns; missing {missing_mapping_sources}"
            )
        canonical_names = tuple(self.normalizedColumnMapping.values())
        if len(set(canonical_names)) != len(canonical_names):
            raise ValueError(f"file {self.fileName}: canonical mapping targets must be unique")

        if self.granularityColumn is not None and self.granularityColumn not in required:
            raise ValueError(
                f"file {self.fileName}: granularityColumn {self.granularityColumn!r} must "
                "also be a raw required column"
            )
        if self.granularityRowCounts is not None and any(
            count < 0 for count in self.granularityRowCounts.values()
        ):
            raise ValueError(f"file {self.fileName}: granularity row counts cannot be negative")

        constrained = set(self.allowedColumnValues)
        missing_constrained = sorted(constrained - required)
        if missing_constrained:
            raise ValueError(
                f"file {self.fileName}: allowedColumnValues columns must also be raw "
                f"requiredColumns; missing {missing_constrained}"
            )
        if any(not values for values in self.allowedColumnValues.values()):
            raise ValueError(f"file {self.fileName}: allowedColumnValues cannot contain empty sets")
        return self


class DatasetAssetManifest(StrictModel):
    """The checked-in catalog record for one external dataset bundle."""

    assetId: NonEmptyStr
    manifestVersion: NonEmptyStr
    bundleFileName: NonEmptyStr
    bundleSha256: NonEmptyStr
    #: Only primary manifests are run by CLI ``--bundle`` / ``--all``. A non-primary record
    #: may expose a file-level catalog alias without re-validating the same ZIP as a bundle.
    validationPrimary: bool = True
    domain: DatasetDomain
    evidenceLevel: DatasetEvidenceLevel
    roles: tuple[DatasetRole, ...]
    allowedModelTasks: tuple[ModelTask, ...]
    licenseEligibility: LicenseEligibility
    licenseNotes: str | None = None
    eligibility: DatasetEligibility
    productionTrainingEligible: bool = False
    continuousCurveGroundTruth: bool = False
    officialDistanceAuthority: bool = False
    files: tuple[DatasetFileManifest, ...]
    restrictions: tuple[DatasetRestriction, ...] = ()
    leakageRules: tuple[NonEmptyStr, ...] = ()
    qaWarnings: tuple[str, ...] = ()
    sourceDescription: str | None = None

    @model_validator(mode="after")
    def _check_rules(self) -> DatasetAssetManifest:
        _check_sha256(self.bundleSha256, "bundleSha256")
        if not self.files:
            raise ValueError("a dataset asset needs at least one file manifest")
        _check_eligibility_policy(
            label=f"asset {self.assetId}",
            roles=self.roles,
            allowed_tasks=self.allowedModelTasks,
            license_eligibility=self.licenseEligibility,
            eligibility=self.eligibility,
            production_training_eligible=self.productionTrainingEligible,
        )
        if self.continuousCurveGroundTruth and self.evidenceLevel in (
            DatasetEvidenceLevel.OFFICIAL_RACE_RESULT,
            DatasetEvidenceLevel.PROCESSED_SENSOR_STATISTIC,
            DatasetEvidenceLevel.UNPROVENANCED,
        ):
            raise ValueError(
                f"evidence level {self.evidenceLevel.value} cannot claim continuousCurveGroundTruth"
            )
        return self


class ProductionViewRequest(StrictModel):
    """A request to build a production or primary-research view from a bundle asset."""

    assetId: NonEmptyStr
    task: ModelTask
    primaryResearch: bool = False


class DatasetFileViewRequest(StrictModel):
    """A request to build a task-specific view from one member of a multi-file bundle."""

    assetId: NonEmptyStr
    fileName: NonEmptyStr
    task: ModelTask
    primaryResearch: bool = False


__all__ = [
    "DatasetAssetManifest",
    "DatasetFileManifest",
    "DatasetFilePolicy",
    "DatasetFileViewRequest",
    "DatasetRestriction",
    "DatasetValidationSummary",
    "ProductionViewRequest",
]
