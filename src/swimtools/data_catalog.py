"""Dataset catalog loading, normalization mappings and eligibility gates.

The catalog describes real raw headers. Canonical research fields are created only through
an explicit raw-to-canonical mapping on :class:`contracts.data_assets.DatasetFileManifest`.
The deterministic runtime never imports this module.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from contracts.data_assets import (
    DatasetAssetManifest,
    DatasetFileManifest,
    DatasetFileViewRequest,
    ProductionViewRequest,
)
from contracts.enums import (
    DatasetEligibility,
    DatasetRole,
    LicenseEligibility,
    ModelTask,
)

DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[2] / "data" / "catalog"
DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "data" / "schemas"


class DatasetCatalogError(Exception):
    """The catalog could not be loaded or a requested asset/file does not exist."""


class DatasetEligibilityError(Exception):
    """A dataset was requested for a use its bundle/file policy forbids."""


@dataclass(frozen=True)
class ResolvedDatasetPolicy:
    """Effective bundle-or-file policy used by the typed eligibility gate."""

    label: str
    roles: tuple[DatasetRole, ...]
    allowedModelTasks: tuple[ModelTask, ...]
    licenseEligibility: LicenseEligibility
    eligibility: DatasetEligibility
    productionTrainingEligible: bool
    continuousCurveGroundTruth: bool
    officialDistanceAuthority: bool


def load_catalog(catalog_dir: Path | None = None) -> dict[str, DatasetAssetManifest]:
    """Load every ``*.json`` manifest, keyed by ``assetId``."""
    directory = catalog_dir if catalog_dir is not None else DEFAULT_CATALOG_DIR
    if not directory.is_dir():
        raise DatasetCatalogError(f"catalog directory not found: {directory}")
    catalog: dict[str, DatasetAssetManifest] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DatasetCatalogError(f"{path.name}: invalid JSON: {exc}") from exc
        manifest = DatasetAssetManifest.model_validate(payload)
        if manifest.assetId in catalog:
            raise DatasetCatalogError(f"duplicate assetId {manifest.assetId} in {path.name}")
        catalog[manifest.assetId] = manifest
    if not catalog:
        raise DatasetCatalogError(f"no manifests found in {directory}")
    return catalog


def load_schemas(schema_dir: Path | None = None) -> dict[str, Mapping[str, object]]:
    """Load checked-in dataset expectation documents, keyed by ``schemaId``."""
    directory = schema_dir if schema_dir is not None else DEFAULT_SCHEMA_DIR
    if not directory.is_dir():
        raise DatasetCatalogError(f"schema directory not found: {directory}")
    schemas: dict[str, Mapping[str, object]] = {}
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_id = str(payload["schemaId"])
        schemas[schema_id] = payload
    return schemas


def schema_for_asset(
    asset_id: str, schemas: Mapping[str, Mapping[str, object]]
) -> Mapping[str, object] | None:
    """Return the expectation document that applies to an asset, if any."""
    for payload in schemas.values():
        applies = payload.get("appliesToAssetIds", ())
        if isinstance(applies, Iterable) and asset_id in tuple(applies):
            return payload
    return None


def get_asset(catalog: Mapping[str, DatasetAssetManifest], asset_id: str) -> DatasetAssetManifest:
    manifest = catalog.get(asset_id)
    if manifest is None:
        raise DatasetCatalogError(f"unknown assetId {asset_id!r}")
    return manifest


def get_file_manifest(manifest: DatasetAssetManifest, file_name: str) -> DatasetFileManifest:
    """Find one member manifest by exact ZIP basename."""
    for member in manifest.files:
        if member.fileName == file_name:
            return member
    raise DatasetCatalogError(f"{manifest.assetId} has no member {file_name!r}")


def primary_validation_manifests(
    catalog: Mapping[str, DatasetAssetManifest], bundle_file_name: str | None = None
) -> tuple[DatasetAssetManifest, ...]:
    """Return unique CLI validation manifests, excluding file-level catalog aliases."""
    manifests = [
        manifest
        for manifest in catalog.values()
        if manifest.validationPrimary
        and (bundle_file_name is None or manifest.bundleFileName == bundle_file_name)
    ]
    by_bundle: dict[str, DatasetAssetManifest] = {}
    for manifest in manifests:
        existing = by_bundle.get(manifest.bundleFileName)
        if existing is not None:
            raise DatasetCatalogError(
                "multiple primary validation manifests for "
                f"{manifest.bundleFileName}: {existing.assetId}, {manifest.assetId}"
            )
        by_bundle[manifest.bundleFileName] = manifest
    return tuple(sorted(by_bundle.values(), key=lambda item: item.bundleFileName))


def resolved_asset_policy(manifest: DatasetAssetManifest) -> ResolvedDatasetPolicy:
    return ResolvedDatasetPolicy(
        label=manifest.assetId,
        roles=manifest.roles,
        allowedModelTasks=manifest.allowedModelTasks,
        licenseEligibility=manifest.licenseEligibility,
        eligibility=manifest.eligibility,
        productionTrainingEligible=manifest.productionTrainingEligible,
        continuousCurveGroundTruth=manifest.continuousCurveGroundTruth,
        officialDistanceAuthority=manifest.officialDistanceAuthority,
    )


def resolved_file_policy(
    manifest: DatasetAssetManifest, member: DatasetFileManifest
) -> ResolvedDatasetPolicy:
    """Resolve a member policy, inheriting the bundle policy when no override is present."""
    policy = member.policy
    if policy is None:
        return ResolvedDatasetPolicy(
            label=f"{manifest.assetId}:{member.fileName}",
            roles=manifest.roles,
            allowedModelTasks=manifest.allowedModelTasks,
            licenseEligibility=manifest.licenseEligibility,
            eligibility=manifest.eligibility,
            productionTrainingEligible=manifest.productionTrainingEligible,
            continuousCurveGroundTruth=manifest.continuousCurveGroundTruth,
            officialDistanceAuthority=manifest.officialDistanceAuthority,
        )
    return ResolvedDatasetPolicy(
        label=f"{manifest.assetId}:{member.fileName}",
        roles=policy.roles,
        allowedModelTasks=policy.allowedModelTasks,
        licenseEligibility=policy.licenseEligibility,
        eligibility=policy.eligibility,
        productionTrainingEligible=policy.productionTrainingEligible,
        continuousCurveGroundTruth=policy.continuousCurveGroundTruth,
        officialDistanceAuthority=policy.officialDistanceAuthority,
    )


def normalize_raw_record(
    raw_record: Mapping[str, str], member: DatasetFileManifest
) -> dict[str, str]:
    """Build a normalized view without pretending canonical names exist in the raw CSV.

    The raw fields are preserved and each declared ``raw -> canonical`` mapping is added as
    a canonical key. A missing mapped raw column is a typed catalog error.
    """
    normalized = dict(raw_record)
    for raw_name, canonical_name in member.normalizedColumnMapping.items():
        if raw_name not in raw_record:
            raise DatasetCatalogError(
                f"{member.fileName}: mapped raw column {raw_name!r} is missing"
            )
        normalized[canonical_name] = raw_record[raw_name]
    return normalized


def _assert_policy_allowed(
    policy: ResolvedDatasetPolicy, *, task: ModelTask, primary_research: bool
) -> None:
    quarantined = policy.eligibility in (
        DatasetEligibility.QUARANTINED,
        DatasetEligibility.SMOKE_TEST_ONLY,
    )
    if quarantined:
        if task is not ModelTask.PIPELINE_SMOKE_TEST:
            raise DatasetEligibilityError(
                f"{policy.label} is {policy.eligibility.value}: only PIPELINE_SMOKE_TEST "
                f"is permitted, not {task.value}"
            )
        if primary_research:
            raise DatasetEligibilityError(
                f"{policy.label} is {policy.eligibility.value}: it may not enter primary "
                "research analysis"
            )
        return

    if task not in policy.allowedModelTasks:
        raise DatasetEligibilityError(
            f"{policy.label} does not allow task {task.value}; allowed: "
            f"{[allowed.value for allowed in policy.allowedModelTasks]}"
        )

    if primary_research:
        if policy.eligibility not in (
            DatasetEligibility.RESEARCH_ELIGIBLE,
            DatasetEligibility.PRODUCTION_ELIGIBLE,
        ):
            raise DatasetEligibilityError(
                f"{policy.label} is {policy.eligibility.value}: primary research is blocked"
            )
        if policy.licenseEligibility is LicenseEligibility.BLOCKED:
            raise DatasetEligibilityError(f"{policy.label} license is BLOCKED")
        return

    if task is ModelTask.PIPELINE_SMOKE_TEST:
        return
    if not policy.productionTrainingEligible:
        raise DatasetEligibilityError(
            f"{policy.label} is not production training eligible "
            f"(license={policy.licenseEligibility.value}, "
            f"eligibility={policy.eligibility.value})"
        )
    if policy.licenseEligibility is not LicenseEligibility.VERIFIED_ALLOWED:
        raise DatasetEligibilityError(
            f"{policy.label} license is {policy.licenseEligibility.value}; production use "
            "requires VERIFIED_ALLOWED"
        )


def assert_view_allowed(
    catalog: Mapping[str, DatasetAssetManifest], request: ProductionViewRequest
) -> DatasetAssetManifest:
    """Gate a bundle-level production or primary-research request."""
    manifest = get_asset(catalog, request.assetId)
    if request.primaryResearch and any(member.policy is not None for member in manifest.files):
        raise DatasetEligibilityError(
            f"{manifest.assetId} has file-level policies; request a specific member view"
        )
    _assert_policy_allowed(
        resolved_asset_policy(manifest),
        task=request.task,
        primary_research=request.primaryResearch,
    )
    return manifest


def assert_file_view_allowed(
    catalog: Mapping[str, DatasetAssetManifest], request: DatasetFileViewRequest
) -> DatasetFileManifest:
    """Gate one file-level view inside a multi-file bundle."""
    manifest = get_asset(catalog, request.assetId)
    member = get_file_manifest(manifest, request.fileName)
    _assert_policy_allowed(
        resolved_file_policy(manifest, member),
        task=request.task,
        primary_research=request.primaryResearch,
    )
    return member


def assert_not_measured_velocity_target(manifest: DatasetAssetManifest) -> None:
    """Deny using a bundle as measured continuous-velocity model target."""
    if not manifest.continuousCurveGroundTruth:
        raise DatasetEligibilityError(
            f"{manifest.assetId} is not continuous-velocity ground truth; it may only "
            "inform a target envelope, never a measured-velocity target"
        )


__all__ = [
    "DEFAULT_CATALOG_DIR",
    "DEFAULT_SCHEMA_DIR",
    "DatasetCatalogError",
    "DatasetEligibilityError",
    "ResolvedDatasetPolicy",
    "assert_file_view_allowed",
    "assert_not_measured_velocity_target",
    "assert_view_allowed",
    "get_asset",
    "get_file_manifest",
    "load_catalog",
    "load_schemas",
    "normalize_raw_record",
    "primary_validation_manifests",
    "resolved_asset_policy",
    "resolved_file_policy",
    "schema_for_asset",
]
