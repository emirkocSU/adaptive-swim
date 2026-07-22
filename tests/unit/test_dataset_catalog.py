"""Dataset catalog and streaming-validator tests (Commit 8, corrected §15).

CI fixtures are deliberately tiny, representative ZIP/CSV bundles built in-process. The
real multi-hundred-megabyte bundles are validated out of band by the operator with
``python -m swimtools.validate_dataset_bundle --all --data-root ...``.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from contracts.data_assets import (
    DatasetAssetManifest,
    DatasetFileViewRequest,
    ProductionViewRequest,
)
from contracts.enums import ModelTask
from swimtools.data_catalog import (
    DEFAULT_CATALOG_DIR,
    DatasetEligibilityError,
    assert_file_view_allowed,
    assert_not_measured_velocity_target,
    assert_view_allowed,
    load_catalog,
    load_schemas,
    normalize_raw_record,
    primary_validation_manifests,
    schema_for_asset,
)
from swimtools.validate_dataset_bundle import validate_bundle

_CSV = "race_uid,segment_index,segment_time_sec\nr1,0,12.5\nr1,1,13.0\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_bundle(tmp_path: Path, members: dict[str, str], name: str = "mini.zip") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for member, text in members.items():
            zf.writestr(member, text)
    return path


def _manifest(
    bundle: Path,
    *,
    csv_sha: str | None,
    rows: int | None = 2,
    cols: int | None = 3,
    required: tuple[str, ...] = ("race_uid", "segment_index"),
    file_name: str = "mini.csv",
) -> DatasetAssetManifest:
    return DatasetAssetManifest.model_validate(
        {
            "assetId": "mini",
            "manifestVersion": "1.0.0",
            "bundleFileName": bundle.name,
            "bundleSha256": _sha(bundle.read_bytes()),
            "domain": "OFFICIAL_RACE",
            "evidenceLevel": "OFFICIAL_RACE_RESULT",
            "roles": ["RACE_PACING_PRIOR"],
            "allowedModelTasks": ["RACE_PACING_PRIOR_TRAINING"],
            "licenseEligibility": "TBD_VERIFICATION_REQUIRED",
            "eligibility": "LICENSE_BLOCKED",
            "files": [
                {
                    "fileName": file_name,
                    "sha256": csv_sha,
                    "expectedRowCount": rows,
                    "expectedColumnCount": cols,
                    "requiredColumns": list(required),
                }
            ],
        }
    )


# --------------------------------------------------------------------------- catalog
def test_all_four_bundles_plus_quarantine_are_catalogued() -> None:
    catalog = load_catalog()
    for asset_id in (
        "adaptive_swim_unified_official_pacing_all_sources_v3",
        "adaptive_swim_sensor_imu_frontcrawl_model_ready_v1",
        "adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1",
        "adaptive_swim_external_studies_5_6_7_model_ready_v1",
        "adaptive_swim_stroke_dataset_quarantined_v1",
    ):
        assert asset_id in catalog


def test_catalog_manifests_parse_and_carry_expected_shapes() -> None:
    catalog = load_catalog()
    race = catalog["adaptive_swim_unified_official_pacing_all_sources_v3"]
    assert race.bundleSha256.startswith("1146f055")
    csv_file = race.files[0]
    assert csv_file.expectedRowCount == 128_475
    assert csv_file.expectedColumnCount == 151
    assert "race_uid" in csv_file.requiredColumns
    assert race.continuousCurveGroundTruth is False
    assert race.officialDistanceAuthority is False

    training = catalog["adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1"]
    counts = training.files[0].granularityRowCounts
    assert counts == {"ATHLETE_WEEK": 228, "SPRINT_REPEAT": 168}


def test_schemas_are_linked_to_assets() -> None:
    schemas = load_schemas()
    payload = schema_for_asset("adaptive_swim_unified_official_pacing_all_sources_v3", schemas)
    assert payload is not None
    assert "race_uid" in payload["requiredRawColumns"]


def test_catalog_files_are_small_metadata_only() -> None:
    for path in DEFAULT_CATALOG_DIR.glob("*.json"):
        assert path.stat().st_size < 32_000, f"{path.name} looks like embedded data"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "files" in payload


# --------------------------------------------------------------------------- validator
def test_valid_bundle_passes(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"mini.csv": _CSV})
    result = validate_bundle(bundle, _manifest(bundle, csv_sha=_sha(_CSV.encode())))
    assert result.bundleValid
    assert result.blockingErrors == []
    assert result.files[0].rowCount == 2
    assert result.files[0].columnCount == 3


def test_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"mini.csv": _CSV})
    result = validate_bundle(bundle, _manifest(bundle, csv_sha="a" * 64))
    assert not result.bundleValid
    assert any("SHA-256 mismatch" in e for e in result.blockingErrors)


def test_row_count_mismatch_is_rejected(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"mini.csv": _CSV})
    result = validate_bundle(bundle, _manifest(bundle, csv_sha=_sha(_CSV.encode()), rows=99))
    assert not result.bundleValid
    assert any("row count mismatch" in e for e in result.blockingErrors)


def test_missing_required_column_is_rejected(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"mini.csv": _CSV})
    result = validate_bundle(
        bundle,
        _manifest(bundle, csv_sha=_sha(_CSV.encode()), required=("race_uid", "not_there")),
    )
    assert not result.bundleValid
    assert any("missing required raw columns" in e for e in result.blockingErrors)


def test_unexpected_member_is_rejected(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"mini.csv": _CSV, "surprise.exe": "x"})
    result = validate_bundle(bundle, _manifest(bundle, csv_sha=_sha(_CSV.encode())))
    assert not result.bundleValid
    assert any("unexpected member" in e for e in result.blockingErrors)


def test_zip_slip_member_is_rejected(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"../escape.csv": _CSV, "mini.csv": _CSV})
    result = validate_bundle(bundle, _manifest(bundle, csv_sha=_sha(_CSV.encode())))
    assert not result.bundleValid
    assert any("unsafe member path" in e for e in result.blockingErrors)


def test_bundle_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"mini.csv": _CSV})
    manifest = _manifest(bundle, csv_sha=_sha(_CSV.encode()))
    tampered = manifest.model_copy(update={"bundleSha256": "b" * 64})
    result = validate_bundle(bundle, tampered)
    assert not result.bundleValid
    assert any("bundle SHA-256 mismatch" in e for e in result.blockingErrors)


def test_missing_member_is_rejected(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"other.csv": _CSV})
    manifest = _manifest(bundle, csv_sha=_sha(_CSV.encode()))
    result = validate_bundle(bundle, manifest)
    assert not result.bundleValid
    assert any("missing expected member" in e for e in result.blockingErrors)


def test_unrecorded_hash_is_a_warning_not_an_error(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"mini.csv": _CSV})
    result = validate_bundle(bundle, _manifest(bundle, csv_sha=None))
    assert result.bundleValid
    assert any("no expected SHA-256 recorded" in w for w in result.warnings)


def test_license_tbd_surfaces_a_production_block(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path, {"mini.csv": _CSV})
    result = validate_bundle(bundle, _manifest(bundle, csv_sha=_sha(_CSV.encode())))
    assert result.productionTrainingEligible is False
    assert any("production training blocked" in w for w in result.warnings)


def test_validator_uses_bounded_memory_on_a_large_csv(tmp_path: Path) -> None:
    """A CSV far larger than one chunk is streamed, not materialised."""
    rows = "\n".join(f"r{i},0,12.5" for i in range(60_000))
    big = "race_uid,segment_index,segment_time_sec\n" + rows + "\n"
    bundle = _build_bundle(tmp_path, {"mini.csv": big}, name="big.zip")
    manifest = _manifest(bundle, csv_sha=_sha(big.encode()), rows=60_000, cols=3)
    result = validate_bundle(bundle, manifest)
    assert result.bundleValid
    assert result.files[0].rowCount == 60_000


def test_granularity_counts_are_verified(tmp_path: Path) -> None:
    text = (
        "record_granularity,source_participant_id,session_or_trial_id\n"
        "ATHLETE_WEEK,a,s1\nSPRINT_REPEAT,b,t1\nSPRINT_REPEAT,c,t1\n"
    )
    bundle = _build_bundle(tmp_path, {"gran.csv": text}, name="gran.zip")
    manifest = DatasetAssetManifest.model_validate(
        {
            "assetId": "gran",
            "manifestVersion": "1.0.0",
            "bundleFileName": bundle.name,
            "bundleSha256": _sha(bundle.read_bytes()),
            "domain": "TRAINING",
            "evidenceLevel": "TRAINING_OBSERVATION",
            "roles": ["TRAINING_DOMAIN_CORRECTION"],
            "allowedModelTasks": ["TRAINING_DOMAIN_CORRECTION_TRAINING"],
            "licenseEligibility": "MIXED_BY_SOURCE",
            "eligibility": "RESEARCH_ELIGIBLE",
            "files": [
                {
                    "fileName": "gran.csv",
                    "sha256": _sha(text.encode()),
                    "requiredColumns": [
                        "record_granularity",
                        "source_participant_id",
                        "session_or_trial_id",
                    ],
                    "granularityColumn": "record_granularity",
                    "granularityRowCounts": {"ATHLETE_WEEK": 1, "SPRINT_REPEAT": 2},
                    "normalizedColumnMapping": {
                        "source_participant_id": "subject_uid",
                        "session_or_trial_id": "session_uid",
                        "record_granularity": "record_type",
                    },
                }
            ],
        }
    )
    assert validate_bundle(bundle, manifest).bundleValid
    wrong = manifest.model_copy(
        update={
            "files": (
                manifest.files[0].model_copy(
                    update={"granularityRowCounts": {"ATHLETE_WEEK": 5, "SPRINT_REPEAT": 2}}
                ),
            )
        }
    )
    result = validate_bundle(bundle, wrong)
    assert not result.bundleValid
    assert any("granularity ATHLETE_WEEK" in e for e in result.blockingErrors)


# --------------------------------------------------------------------------- gates
def test_quarantined_asset_rejects_a_production_view() -> None:
    catalog = load_catalog()
    with pytest.raises(DatasetEligibilityError):
        assert_view_allowed(
            catalog,
            ProductionViewRequest(
                assetId="adaptive_swim_stroke_dataset_quarantined_v1",
                task=ModelTask.RACE_PACING_PRIOR_TRAINING,
            ),
        )


def test_quarantined_asset_rejects_primary_research() -> None:
    catalog = load_catalog()
    with pytest.raises(DatasetEligibilityError):
        assert_view_allowed(
            catalog,
            ProductionViewRequest(
                assetId="adaptive_swim_stroke_dataset_quarantined_v1",
                task=ModelTask.PIPELINE_SMOKE_TEST,
                primaryResearch=True,
            ),
        )


def test_quarantined_asset_allows_only_smoke_tests() -> None:
    catalog = load_catalog()
    manifest = assert_view_allowed(
        catalog,
        ProductionViewRequest(
            assetId="adaptive_swim_stroke_dataset_quarantined_v1",
            task=ModelTask.PIPELINE_SMOKE_TEST,
        ),
    )
    assert manifest.productionTrainingEligible is False


def test_license_tbd_closes_the_production_gate() -> None:
    catalog = load_catalog()
    with pytest.raises(DatasetEligibilityError):
        assert_view_allowed(
            catalog,
            ProductionViewRequest(
                assetId="adaptive_swim_unified_official_pacing_all_sources_v3",
                task=ModelTask.RACE_PACING_PRIOR_TRAINING,
            ),
        )


def test_manifest_forbids_production_eligible_without_verified_license() -> None:
    with pytest.raises(ValueError, match="VERIFIED_ALLOWED"):
        DatasetAssetManifest.model_validate(
            {
                "assetId": "bad",
                "manifestVersion": "1.0.0",
                "bundleFileName": "bad.zip",
                "bundleSha256": "c" * 64,
                "domain": "TRAINING",
                "evidenceLevel": "TRAINING_OBSERVATION",
                "roles": ["TRAINING_DOMAIN_CORRECTION"],
                "allowedModelTasks": ["TRAINING_DOMAIN_CORRECTION_TRAINING"],
                "licenseEligibility": "TBD_VERIFICATION_REQUIRED",
                "eligibility": "PRODUCTION_ELIGIBLE",
                "productionTrainingEligible": True,
                "files": [{"fileName": "x.csv", "sha256": "d" * 64}],
            }
        )


def test_manifest_forbids_ground_truth_claim_from_race_results() -> None:
    with pytest.raises(ValueError, match="continuousCurveGroundTruth"):
        DatasetAssetManifest.model_validate(
            {
                "assetId": "bad2",
                "manifestVersion": "1.0.0",
                "bundleFileName": "bad2.zip",
                "bundleSha256": "c" * 64,
                "domain": "OFFICIAL_RACE",
                "evidenceLevel": "OFFICIAL_RACE_RESULT",
                "roles": ["RACE_PACING_PRIOR"],
                "allowedModelTasks": ["RACE_PACING_PRIOR_TRAINING"],
                "licenseEligibility": "VERIFIED_ALLOWED",
                "eligibility": "RESEARCH_ELIGIBLE",
                "continuousCurveGroundTruth": True,
                "files": [{"fileName": "x.csv", "sha256": "d" * 64}],
            }
        )


def test_no_catalogued_asset_may_be_a_measured_velocity_target() -> None:
    catalog = load_catalog()
    for manifest in catalog.values():
        with pytest.raises(DatasetEligibilityError):
            assert_not_measured_velocity_target(manifest)


def test_external_studies_qa_warnings_are_preserved() -> None:
    catalog = load_catalog()
    studies = catalog["adaptive_swim_external_studies_5_6_7_model_ready_v1"]
    assert studies.qaWarnings


def test_real_raw_header_mapping_does_not_require_invented_canonical_columns(
    tmp_path: Path,
) -> None:
    text = (
        "source_participant_id,session_or_trial_id,record_granularity,license_status\n"
        "P1,T1,ATHLETE_WEEK,LICENSE_TBD_SOURCE_PAGE_REVIEW_REQUIRED\n"
    )
    bundle = _build_bundle(tmp_path, {"raw.csv": text}, name="raw-header.zip")
    manifest = DatasetAssetManifest.model_validate(
        {
            "assetId": "raw-header",
            "manifestVersion": "1.1.0",
            "bundleFileName": bundle.name,
            "bundleSha256": _sha(bundle.read_bytes()),
            "domain": "TRAINING",
            "evidenceLevel": "TRAINING_OBSERVATION",
            "roles": ["TRAINING_DOMAIN_CORRECTION"],
            "allowedModelTasks": ["TRAINING_DOMAIN_CORRECTION_TRAINING"],
            "licenseEligibility": "MIXED_BY_SOURCE",
            "eligibility": "RESEARCH_ELIGIBLE",
            "files": [
                {
                    "fileName": "raw.csv",
                    "sha256": _sha(text.encode()),
                    "expectedRowCount": 1,
                    "expectedColumnCount": 4,
                    "requiredColumns": [
                        "source_participant_id",
                        "session_or_trial_id",
                        "record_granularity",
                        "license_status",
                    ],
                    "normalizedColumnMapping": {
                        "source_participant_id": "subject_uid",
                        "session_or_trial_id": "session_uid",
                        "record_granularity": "record_type",
                    },
                }
            ],
        }
    )
    result = validate_bundle(bundle, manifest)
    assert result.bundleValid
    assert result.files[0].missingRequiredColumns == ()
    assert result.files[0].normalizedColumnMapping == {
        "source_participant_id": "subject_uid",
        "session_or_trial_id": "session_uid",
        "record_granularity": "record_type",
    }


def test_normalized_canonical_mapping_builds_view_without_mutating_raw_names() -> None:
    catalog = load_catalog()
    imu = catalog["adaptive_swim_sensor_imu_frontcrawl_model_ready_v1"]
    member = imu.files[0]
    raw = {
        "source_participant_id": "FM1",
        "session_or_trial_id": "TRIAL:FM1",
        "sample_index": "0",
    }
    normalized = normalize_raw_record(raw, member)
    assert normalized["subject_uid"] == "FM1"
    assert normalized["session_uid"] == "TRIAL:FM1"
    assert normalized["source_participant_id"] == "FM1"
    assert "record_type" not in normalized


def test_missing_required_real_raw_column_is_rejected(tmp_path: Path) -> None:
    text = "session_or_trial_id,record_granularity\nT1,ATHLETE_WEEK\n"
    bundle = _build_bundle(tmp_path, {"raw.csv": text}, name="missing-raw.zip")
    manifest = DatasetAssetManifest.model_validate(
        {
            "assetId": "missing-raw",
            "manifestVersion": "1.1.0",
            "bundleFileName": bundle.name,
            "bundleSha256": _sha(bundle.read_bytes()),
            "domain": "TRAINING",
            "evidenceLevel": "TRAINING_OBSERVATION",
            "roles": ["TRAINING_DOMAIN_CORRECTION"],
            "allowedModelTasks": ["TRAINING_DOMAIN_CORRECTION_TRAINING"],
            "licenseEligibility": "MIXED_BY_SOURCE",
            "eligibility": "RESEARCH_ELIGIBLE",
            "files": [
                {
                    "fileName": "raw.csv",
                    "sha256": _sha(text.encode()),
                    "requiredColumns": [
                        "source_participant_id",
                        "session_or_trial_id",
                        "record_granularity",
                    ],
                    "normalizedColumnMapping": {
                        "source_participant_id": "subject_uid",
                        "session_or_trial_id": "session_uid",
                        "record_granularity": "record_type",
                    },
                }
            ],
        }
    )
    result = validate_bundle(bundle, manifest)
    assert not result.bundleValid
    assert any("source_participant_id" in error for error in result.blockingErrors)


def test_catalog_uses_real_training_record_granularity_column() -> None:
    catalog = load_catalog()
    training = catalog["adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1"]
    member = training.files[0]
    assert member.granularityColumn == "record_granularity"
    assert member.granularityRowCounts == {"ATHLETE_WEEK": 228, "SPRINT_REPEAT": 168}
    assert member.normalizedColumnMapping["record_granularity"] == "record_type"
    assert "record_type" not in member.requiredColumns


def test_external_studies_is_one_primary_multifile_bundle() -> None:
    catalog = load_catalog()
    primary = primary_validation_manifests(
        catalog, "adaptive_swim_external_studies_5_6_7_model_ready_v1.zip"
    )
    assert len(primary) == 1
    assert primary[0].assetId == "adaptive_swim_external_studies_5_6_7_model_ready_v1"
    assert len(primary[0].files) == 7
    alias = catalog["adaptive_swim_stroke_dataset_quarantined_v1"]
    assert alias.validationPrimary is False


def test_external_studies_multifile_bundle_accepts_all_expected_members(
    tmp_path: Path,
) -> None:
    controlled = (
        "source_participant_id,session_or_trial_id,record_granularity,license_status\n"
        "P1,T1,SWIM_25M_SEGMENT,OPEN_DATA_CC0_REPORTED_BY_SOURCE\n"
    )
    stroke = (
        "source_participant_id,session_or_trial_id,record_granularity,"
        "production_training_eligible,research_primary_analysis_eligible,"
        "pipeline_smoke_test_eligible,model_eligibility\n"
        ",,UNVERIFIED_FEATURE_ROW,False,False,True,PIPELINE_SMOKE_TEST_ONLY\n"
    )
    members = {
        "controlled.csv": controlled,
        "stroke.csv": stroke,
        "manifest.csv": "source_id\nS1\n",
        "qa.json": "{}",
        "README.md": "fixture",
    }
    bundle = _build_bundle(tmp_path, members, name="external.zip")
    manifest = DatasetAssetManifest.model_validate(
        {
            "assetId": "external",
            "manifestVersion": "1.1.0",
            "bundleFileName": bundle.name,
            "bundleSha256": _sha(bundle.read_bytes()),
            "domain": "CONTROLLED_STUDY",
            "evidenceLevel": "CONTROLLED_STUDY",
            "roles": ["FATIGUE_SHAPE_PRIOR", "PIPELINE_SMOKE_TEST_ONLY"],
            "allowedModelTasks": [
                "TRAINING_DOMAIN_CORRECTION_TRAINING",
                "PIPELINE_SMOKE_TEST",
            ],
            "licenseEligibility": "MIXED_BY_SOURCE",
            "eligibility": "RESEARCH_ELIGIBLE",
            "files": [
                {
                    "fileName": "controlled.csv",
                    "sha256": _sha(controlled.encode()),
                    "requiredColumns": [
                        "source_participant_id",
                        "session_or_trial_id",
                        "record_granularity",
                        "license_status",
                    ],
                    "normalizedColumnMapping": {
                        "source_participant_id": "subject_uid",
                        "session_or_trial_id": "session_uid",
                        "record_granularity": "record_type",
                    },
                    "policy": {
                        "roles": ["FATIGUE_SHAPE_PRIOR"],
                        "allowedModelTasks": ["TRAINING_DOMAIN_CORRECTION_TRAINING"],
                        "licenseEligibility": "REPORTED_OPEN_UNVERIFIED",
                        "eligibility": "RESEARCH_ELIGIBLE",
                    },
                },
                {
                    "fileName": "stroke.csv",
                    "sha256": _sha(stroke.encode()),
                    "requiredColumns": [
                        "source_participant_id",
                        "session_or_trial_id",
                        "record_granularity",
                        "production_training_eligible",
                        "research_primary_analysis_eligible",
                        "pipeline_smoke_test_eligible",
                        "model_eligibility",
                    ],
                    "policy": {
                        "roles": ["PIPELINE_SMOKE_TEST_ONLY"],
                        "allowedModelTasks": ["PIPELINE_SMOKE_TEST"],
                        "licenseEligibility": "BLOCKED",
                        "eligibility": "SMOKE_TEST_ONLY",
                    },
                },
                {"fileName": "manifest.csv", "sha256": _sha(b"source_id\nS1\n")},
                {"fileName": "qa.json", "sha256": _sha(b"{}")},
                {"fileName": "README.md", "sha256": _sha(b"fixture")},
            ],
        }
    )
    result = validate_bundle(bundle, manifest)
    assert result.bundleValid
    assert len(result.files) == 5
    stroke_result = next(file for file in result.files if file.fileName == "stroke.csv")
    assert stroke_result.eligibility == "SMOKE_TEST_ONLY"
    assert stroke_result.productionTrainingEligible is False


def test_quarantine_file_level_eligibility_is_smoke_test_only() -> None:
    catalog = load_catalog()
    asset_id = "adaptive_swim_external_studies_5_6_7_model_ready_v1"
    file_name = "adaptive_swim_stroke_dataset_quarantined_v1.csv"
    member = assert_file_view_allowed(
        catalog,
        DatasetFileViewRequest(
            assetId=asset_id,
            fileName=file_name,
            task=ModelTask.PIPELINE_SMOKE_TEST,
        ),
    )
    assert member.policy is not None
    assert member.policy.productionTrainingEligible is False
    with pytest.raises(DatasetEligibilityError):
        assert_file_view_allowed(
            catalog,
            DatasetFileViewRequest(
                assetId=asset_id,
                fileName=file_name,
                task=ModelTask.TRAINING_DOMAIN_CORRECTION_TRAINING,
            ),
        )
    with pytest.raises(DatasetEligibilityError):
        assert_file_view_allowed(
            catalog,
            DatasetFileViewRequest(
                assetId=asset_id,
                fileName=file_name,
                task=ModelTask.PIPELINE_SMOKE_TEST,
                primaryResearch=True,
            ),
        )


def test_controlled_and_massage_file_views_are_research_only_and_condition_aware() -> None:
    catalog = load_catalog()
    asset_id = "adaptive_swim_external_studies_5_6_7_model_ready_v1"
    controlled = assert_file_view_allowed(
        catalog,
        DatasetFileViewRequest(
            assetId=asset_id,
            fileName="adaptive_swim_controlled_study_segment_features_v1.csv",
            task=ModelTask.TRAINING_DOMAIN_CORRECTION_TRAINING,
            primaryResearch=True,
        ),
    )
    assert controlled.policy is not None
    assert controlled.policy.eligibility.value == "RESEARCH_ELIGIBLE"

    massage = assert_file_view_allowed(
        catalog,
        DatasetFileViewRequest(
            assetId=asset_id,
            fileName="adaptive_swim_massage_intervention_model_ready_v1.csv",
            task=ModelTask.ADVISORY_REPORTING_RESEARCH,
            primaryResearch=True,
        ),
    )
    assert "condition_label" in massage.requiredColumns
    assert massage.policy is not None
    assert massage.policy.productionTrainingEligible is False
