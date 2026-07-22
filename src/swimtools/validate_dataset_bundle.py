"""Streaming validator for the real external dataset ZIP bundles.

The validator checks ZIP identity, exact members, per-member hashes, row/column counts,
*raw* required headers, real granularity discriminators and selected raw value constraints.
Canonical research fields are reported from the manifest's explicit raw-to-canonical mapping;
they are never searched for as invented raw headers.

The external-studies package is one multi-file bundle. Its quarantined stroke CSV is exposed
as a file-level ``SMOKE_TEST_ONLY`` policy and is not revalidated as a second bundle by
``--bundle`` or ``--all``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from contracts.data_assets import DatasetAssetManifest, DatasetFileManifest
from contracts.enums import DatasetEligibility, LicenseEligibility
from swimtools.data_catalog import (
    DatasetCatalogError,
    load_catalog,
    load_schemas,
    primary_validation_manifests,
    resolved_file_policy,
    schema_for_asset,
)

_CHUNK = 1 << 20
_MAX_FIELD_BYTES = 1 << 20
_MAX_INVALID_VALUE_SAMPLES = 20

csv.field_size_limit(_MAX_FIELD_BYTES)


@dataclass
class FileValidation:
    fileName: str
    measuredSha256: str
    expectedSha256: str | None
    rowCount: int | None
    columnCount: int | None
    expectedRowCount: int | None
    expectedColumnCount: int | None
    roles: tuple[str, ...] = ()
    licenseStatus: str = ""
    eligibility: str = ""
    productionTrainingEligible: bool = False
    continuousCurveGroundTruth: bool = False
    officialDistanceAuthority: bool = False
    normalizedColumnMapping: dict[str, str] = field(default_factory=dict)
    missingRequiredColumns: tuple[str, ...] = ()
    granularityRowCounts: dict[str, int] = field(default_factory=dict)
    invalidColumnValues: dict[str, dict[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blockingErrors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "fileName": self.fileName,
            "measuredSha256": self.measuredSha256,
            "expectedSha256": self.expectedSha256,
            "rowCount": self.rowCount,
            "columnCount": self.columnCount,
            "expectedRowCount": self.expectedRowCount,
            "expectedColumnCount": self.expectedColumnCount,
            "roles": list(self.roles),
            "licenseStatus": self.licenseStatus,
            "eligibility": self.eligibility,
            "productionTrainingEligible": self.productionTrainingEligible,
            "continuousCurveGroundTruth": self.continuousCurveGroundTruth,
            "officialDistanceAuthority": self.officialDistanceAuthority,
            "normalizedColumnMapping": dict(self.normalizedColumnMapping),
            "missingRequiredColumns": list(self.missingRequiredColumns),
            "granularityRowCounts": dict(self.granularityRowCounts),
            "invalidColumnValues": {
                column: dict(values) for column, values in self.invalidColumnValues.items()
            },
            "warnings": list(self.warnings),
            "blockingErrors": list(self.blockingErrors),
        }


@dataclass
class BundleValidation:
    assetId: str
    bundlePath: str
    bundleValid: bool
    measuredBundleSha256: str
    expectedBundleSha256: str
    files: list[FileValidation] = field(default_factory=list)
    roles: tuple[str, ...] = ()
    licenseStatus: str = ""
    eligibility: str = ""
    productionTrainingEligible: bool = False
    continuousCurveGroundTruth: bool = False
    officialDistanceAuthority: bool = False
    warnings: list[str] = field(default_factory=list)
    blockingErrors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "assetId": self.assetId,
            "bundlePath": self.bundlePath,
            "bundleValid": self.bundleValid,
            "measuredBundleSha256": self.measuredBundleSha256,
            "expectedBundleSha256": self.expectedBundleSha256,
            "files": [file.as_dict() for file in self.files],
            "rowCounts": {file.fileName: file.rowCount for file in self.files},
            "columnCounts": {file.fileName: file.columnCount for file in self.files},
            "hashes": {file.fileName: file.measuredSha256 for file in self.files},
            "roles": list(self.roles),
            "licenseStatus": self.licenseStatus,
            "eligibility": self.eligibility,
            "productionTrainingEligible": self.productionTrainingEligible,
            "continuousCurveGroundTruth": self.continuousCurveGroundTruth,
            "officialDistanceAuthority": self.officialDistanceAuthority,
            "warnings": list(self.warnings),
            "blockingErrors": list(self.blockingErrors),
        }


def _sha256_of_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _is_unsafe_member(name: str) -> bool:
    if name.startswith("/") or name.startswith("\\"):
        return True
    if ":" in name.split("/")[0]:
        return True
    return any(part == ".." for part in Path(name).parts)


def _member_basename(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def _record_invalid_value(
    invalid: dict[str, dict[str, int]], column: str, value: str
) -> None:
    values = invalid.setdefault(column, {})
    if value in values:
        values[value] += 1
    elif len(values) < _MAX_INVALID_VALUE_SAMPLES:
        values[value] = 1
    else:
        values["<additional distinct values>"] = values.get("<additional distinct values>", 0) + 1


def _stream_member(
    zf: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    manifest: DatasetAssetManifest,
    manifest_file: DatasetFileManifest,
) -> FileValidation:
    """Hash and structurally inspect one member in a single bounded-memory pass."""
    expected_sha = manifest_file.sha256
    expected_rows = manifest_file.expectedRowCount
    expected_cols = manifest_file.expectedColumnCount
    name = _member_basename(info.filename)
    digest = hashlib.sha256()
    row_count: int | None = None
    column_count: int | None = None
    missing: tuple[str, ...] = ()
    granularity_counts: dict[str, int] = {}
    invalid_values: dict[str, dict[str, int]] = {}
    warnings: list[str] = []
    errors: list[str] = []

    policy = resolved_file_policy(manifest, manifest_file)
    is_csv = name.lower().endswith(".csv")
    with zf.open(info, "r") as raw:
        if not is_csv:
            while chunk := raw.read(_CHUNK):
                digest.update(chunk)
        else:
            reader = csv.reader(_hashing_text_lines(raw, digest))
            try:
                header = next(reader)
                if header:
                    header[0] = header[0].lstrip("\ufeff")
            except StopIteration:
                errors.append("CSV is empty (no header row)")
                header = []
            column_count = len(header)
            header_set = set(header)
            missing = tuple(
                column for column in manifest_file.requiredColumns if column not in header_set
            )
            granularity_column = manifest_file.granularityColumn
            granularity_index = (
                header.index(granularity_column)
                if granularity_column is not None and granularity_column in header_set
                else None
            )
            constrained_indexes = {
                column: header.index(column)
                for column in manifest_file.allowedColumnValues
                if column in header_set
            }
            allowed_values = {
                column: set(values)
                for column, values in manifest_file.allowedColumnValues.items()
            }

            count = 0
            for row in reader:
                count += 1
                if granularity_index is not None:
                    value = row[granularity_index] if granularity_index < len(row) else ""
                    granularity_counts[value] = granularity_counts.get(value, 0) + 1
                for column, index in constrained_indexes.items():
                    value = row[index] if index < len(row) else ""
                    if value not in allowed_values[column]:
                        _record_invalid_value(invalid_values, column, value)
            row_count = count

    measured = digest.hexdigest()
    if expected_sha is None:
        warnings.append(f"no expected SHA-256 recorded; measured {measured}")
    elif measured != expected_sha:
        errors.append(f"SHA-256 mismatch: expected {expected_sha}, measured {measured}")
    if expected_rows is not None and row_count is not None and row_count != expected_rows:
        errors.append(f"row count mismatch: expected {expected_rows}, measured {row_count}")
    if expected_cols is not None and column_count is not None and column_count != expected_cols:
        errors.append(f"column count mismatch: expected {expected_cols}, measured {column_count}")
    if missing:
        errors.append(f"missing required raw columns: {list(missing)}")

    expected_granularity = manifest_file.granularityRowCounts
    if expected_granularity:
        for key, expected_count in expected_granularity.items():
            actual = granularity_counts.get(key, 0)
            if actual != expected_count:
                errors.append(
                    f"granularity {key}: expected {expected_count} rows, measured {actual}"
                )
        unexpected = sorted(set(granularity_counts) - set(expected_granularity))
        if unexpected:
            errors.append(f"unexpected granularity values: {unexpected}")

    for column, values in invalid_values.items():
        errors.append(
            f"column {column} contains values outside "
            f"{list(manifest_file.allowedColumnValues[column])}: {values}"
        )

    return FileValidation(
        fileName=name,
        measuredSha256=measured,
        expectedSha256=expected_sha,
        rowCount=row_count,
        columnCount=column_count,
        expectedRowCount=expected_rows,
        expectedColumnCount=expected_cols,
        roles=tuple(role.value for role in policy.roles),
        licenseStatus=policy.licenseEligibility.value,
        eligibility=policy.eligibility.value,
        productionTrainingEligible=policy.productionTrainingEligible,
        continuousCurveGroundTruth=policy.continuousCurveGroundTruth,
        officialDistanceAuthority=policy.officialDistanceAuthority,
        normalizedColumnMapping=dict(manifest_file.normalizedColumnMapping),
        missingRequiredColumns=missing,
        granularityRowCounts=granularity_counts,
        invalidColumnValues=invalid_values,
        warnings=warnings,
        blockingErrors=errors,
    )


def _hashing_text_lines(stream: IO[bytes], digest: hashlib._Hash) -> Iterator[str]:
    """Yield UTF-8 lines while hashing each raw byte exactly once."""
    pending = b""
    while True:
        chunk = stream.read(_CHUNK)
        if not chunk:
            break
        digest.update(chunk)
        pending += chunk
        *lines, pending = pending.split(b"\n")
        for line in lines:
            yield line.decode("utf-8") + "\n"
    if pending:
        yield pending.decode("utf-8")


def validate_bundle(
    bundle_path: Path,
    manifest: DatasetAssetManifest,
    schema: Mapping[str, object] | None = None,
) -> BundleValidation:
    """Validate one raw bundle against its primary bundle manifest."""
    result = BundleValidation(
        assetId=manifest.assetId,
        bundlePath=str(bundle_path),
        bundleValid=False,
        measuredBundleSha256="",
        expectedBundleSha256=manifest.bundleSha256,
        roles=tuple(role.value for role in manifest.roles),
        licenseStatus=manifest.licenseEligibility.value,
        eligibility=manifest.eligibility.value,
        productionTrainingEligible=manifest.productionTrainingEligible,
        continuousCurveGroundTruth=manifest.continuousCurveGroundTruth,
        officialDistanceAuthority=manifest.officialDistanceAuthority,
    )
    if not bundle_path.is_file():
        result.blockingErrors.append(f"bundle not found: {bundle_path}")
        return result

    result.measuredBundleSha256 = _sha256_of_path(bundle_path)
    if result.measuredBundleSha256 != manifest.bundleSha256:
        result.blockingErrors.append(
            f"bundle SHA-256 mismatch: expected {manifest.bundleSha256}, "
            f"measured {result.measuredBundleSha256}"
        )

    expected_by_name = {member.fileName: member for member in manifest.files}
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(bundle_path) as zf:
            for info in zf.infolist():
                if _is_unsafe_member(info.filename):
                    result.blockingErrors.append(f"unsafe member path rejected: {info.filename}")
                    continue
                if info.is_dir():
                    continue
                base = _member_basename(info.filename)
                if base in seen:
                    result.blockingErrors.append(f"duplicate member name: {base}")
                    continue
                seen.add(base)
                manifest_file = expected_by_name.get(base)
                if manifest_file is None:
                    result.blockingErrors.append(f"unexpected member: {info.filename}")
                    continue
                result.files.append(_stream_member(zf, info, manifest, manifest_file))
    except (UnicodeDecodeError, csv.Error) as exc:
        result.blockingErrors.append(f"CSV decoding/parsing failed: {exc}")
        return result
    except zipfile.BadZipFile as exc:
        result.blockingErrors.append(f"not a readable ZIP: {exc}")
        return result

    for expected_name in expected_by_name:
        if expected_name not in seen:
            result.blockingErrors.append(f"missing expected member: {expected_name}")

    for file_result in result.files:
        result.blockingErrors.extend(
            f"{file_result.fileName}: {error}" for error in file_result.blockingErrors
        )
        result.warnings.extend(
            f"{file_result.fileName}: {warning}" for warning in file_result.warnings
        )

    if manifest.licenseEligibility is not LicenseEligibility.VERIFIED_ALLOWED:
        result.warnings.append(
            f"license {manifest.licenseEligibility.value}: production training blocked"
        )
    if manifest.eligibility in (DatasetEligibility.QUARANTINED, DatasetEligibility.SMOKE_TEST_ONLY):
        result.warnings.append("QUARANTINED / SMOKE_TEST_ONLY: production views are rejected")
    result.warnings.extend(manifest.qaWarnings)
    if schema is not None:
        rules = schema.get("leakageRules", ())
        if isinstance(rules, list):
            result.warnings.extend(f"leakage rule: {rule}" for rule in rules)

    result.bundleValid = not result.blockingErrors
    return result


def _print_text(result: BundleValidation) -> None:
    status = "VALID" if result.bundleValid else "INVALID"
    print(f"[{status}] {result.assetId}  ({result.bundlePath})")
    print(f"  bundle sha256 : {result.measuredBundleSha256}")
    print(f"  expected      : {result.expectedBundleSha256}")
    print(f"  roles         : {', '.join(result.roles)}")
    print(f"  license       : {result.licenseStatus}")
    print(f"  eligibility   : {result.eligibility}")
    print(f"  production    : {result.productionTrainingEligible}")
    print(f"  curve truth   : {result.continuousCurveGroundTruth}")
    print(f"  distance auth : {result.officialDistanceAuthority}")
    for file in result.files:
        print(
            f"  - {file.fileName}: rows={file.rowCount} cols={file.columnCount} "
            f"sha256={file.measuredSha256}"
        )
        if file.roles:
            print(
                f"      roles={','.join(file.roles)} eligibility={file.eligibility} "
                f"production={file.productionTrainingEligible}"
            )
        if file.granularityRowCounts:
            print(f"      granularities={file.granularityRowCounts}")
        if file.normalizedColumnMapping:
            print(f"      normalized={file.normalizedColumnMapping}")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    for error in result.blockingErrors:
        print(f"  BLOCKING: {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="swimtools.validate_dataset_bundle",
        description="Streaming validator for external dataset bundles",
    )
    parser.add_argument("--bundle", type=Path, default=None, help="path to one raw ZIP bundle")
    parser.add_argument("--all", action="store_true", help="validate every primary bundle")
    parser.add_argument("--data-root", type=Path, default=None, help="directory holding raw ZIPs")
    parser.add_argument("--catalog-dir", type=Path, default=None, help="override catalog dir")
    parser.add_argument("--schema-dir", type=Path, default=None, help="override schema dir")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if not args.all and args.bundle is None:
        parser.error("either --bundle or --all is required")
    if args.all and args.data_root is None:
        parser.error("--all requires --data-root")

    try:
        catalog = load_catalog(args.catalog_dir)
        schemas = load_schemas(args.schema_dir)
        if args.bundle is not None:
            manifests = primary_validation_manifests(catalog, args.bundle.name)
            if not manifests:
                print(
                    f"no primary catalogued asset expects a bundle named {args.bundle.name}",
                    file=sys.stderr,
                )
                return 2
            results = [
                validate_bundle(
                    args.bundle,
                    manifest,
                    schema_for_asset(manifest.assetId, schemas),
                )
                for manifest in manifests
            ]
        else:
            assert args.data_root is not None
            results = [
                validate_bundle(
                    args.data_root / manifest.bundleFileName,
                    manifest,
                    schema_for_asset(manifest.assetId, schemas),
                )
                for manifest in primary_validation_manifests(catalog)
            ]
    except DatasetCatalogError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(
            json.dumps(
                [result.as_dict() for result in results],
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
    else:
        for result in results:
            _print_text(result)
            print()
    return 0 if all(result.bundleValid for result in results) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["BundleValidation", "FileValidation", "main", "validate_bundle"]
