"""The Phase 1 verification manifest is canonical and content-addressed (ADR-041 §9)."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from e2e.manifest import (
    PHASE1_MANIFEST_SCHEMA_VERSION,
    CheckStatus,
    Phase1VerificationCheck,
    decode_manifest,
    deterministic_manifest_id,
    encode_manifest,
    finalize_manifest,
)
from e2e.types import Phase1E2EResult

CASE = "coach-profile-reset"

_REQUIRED_FIELDS = (
    "schemaVersion",
    "manifestId",
    "manifestVersion",
    "caseId",
    "caseVersion",
    "scenarioVersion",
    "scenarioDigest",
    "analyticsPolicyDigest",
    "runId",
    "seed",
    "workoutDigest",
    "sourceWorkoutDigest",
    "profileDigests",
    "selectedProfileId",
    "selectedProfileVersion",
    "replacementProfileId",
    "replacementProfileVersion",
    "compiledTimelineDigest",
    "journalSha256",
    "reportSha256",
    "artifactDigests",
    "artifactDigestFileSha256",
    "eventFirstSeq",
    "eventLastSeq",
    "eventCount",
    "batchCount",
    "liveReplayMatch",
    "officialDistanceValid",
    "clockInvariantsValid",
    "profileInvariantsValid",
    "reportValid",
    "canonicalArtifactsValid",
    "checks",
    "warnings",
    "allChecksPassed",
    "runnerVersion",
    "analyticsVersion",
    "compilerVersion",
    "replayVersion",
)


def test_manifest_carries_every_required_field(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    payload = json.loads(run_case(CASE).verificationManifestPath.read_bytes())
    assert set(payload) == set(_REQUIRED_FIELDS)
    assert payload["schemaVersion"] == PHASE1_MANIFEST_SCHEMA_VERSION


def test_manifest_is_canonical_json(run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case(CASE)
    raw = result.verificationManifestPath.read_bytes()
    assert encode_manifest(decode_manifest(raw)) == raw
    assert b"\r\n" not in raw
    assert raw == raw.strip()


def test_manifest_id_is_content_addressed(run_case: Callable[..., Phase1E2EResult]) -> None:
    manifest = run_case(CASE).verificationManifest
    assert manifest.manifestId == deterministic_manifest_id(manifest)
    changed = manifest.model_copy(update={"seed": manifest.seed + 1})
    assert deterministic_manifest_id(changed) != manifest.manifestId


def test_checks_carry_structured_results(run_case: Callable[..., Phase1E2EResult]) -> None:
    manifest = run_case(CASE).verificationManifest
    assert manifest.checks
    ids = [check.checkId for check in manifest.checks]
    assert len(set(ids)) == len(ids)
    for check in manifest.checks:
        assert check.status in {
            CheckStatus.PASS,
            CheckStatus.FAIL,
            CheckStatus.NOT_APPLICABLE,
        }
        assert check.checkId
    assert manifest.allChecksPassed is True


def test_group_flags_agree_with_the_individual_checks(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    manifest = run_case(CASE).verificationManifest
    for prefix, flag in (
        ("state.", manifest.liveReplayMatch),
        ("distance.", manifest.officialDistanceValid),
        ("clock.", manifest.clockInvariantsValid),
        ("profile.", manifest.profileInvariantsValid),
        ("report.", manifest.reportValid),
        ("artifact.", manifest.canonicalArtifactsValid),
    ):
        group = [check for check in manifest.checks if check.checkId.startswith(prefix)]
        assert group, prefix
        assert flag == all(check.status is not CheckStatus.FAIL for check in group)


def test_manifest_records_component_versions(run_case: Callable[..., Phase1E2EResult]) -> None:
    manifest = run_case(CASE).verificationManifest
    assert manifest.runnerVersion.startswith("e2e-runner-")
    assert manifest.analyticsVersion.startswith("analytics-")
    assert manifest.compilerVersion.startswith("continuous-")
    assert manifest.replayVersion.startswith("replay-")


def test_manifest_holds_no_environment_specific_values(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    text = run_case(CASE).verificationManifestPath.read_text(encoding="utf-8")
    for forbidden in ("/tmp", "/home", "C:\\", "file://"):
        assert forbidden not in text


def test_manifest_digests_match_the_bundle(run_case: Callable[..., Phase1E2EResult]) -> None:
    import hashlib

    result = run_case(CASE)
    manifest = result.verificationManifest
    assert manifest.journalSha256 == hashlib.sha256(result.journalPath.read_bytes()).hexdigest()
    assert (
        manifest.reportSha256 == hashlib.sha256(result.sessionReportPath.read_bytes()).hexdigest()
    )
    assert manifest.workoutDigest and manifest.compiledTimelineDigest
    assert manifest.profileDigests
    assert manifest.artifactDigests
    assert manifest.artifactDigestFileSha256


def test_finalized_manifest_is_stable(run_case: Callable[..., Phase1E2EResult]) -> None:
    manifest = run_case(CASE).verificationManifest
    assert finalize_manifest(manifest).manifestId == manifest.manifestId


def test_check_model_rejects_an_empty_id() -> None:
    with pytest.raises(ValueError):
        Phase1VerificationCheck(checkId="", status=CheckStatus.PASS)
