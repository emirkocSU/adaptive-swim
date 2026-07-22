"""Canonical Phase 1 verification manifest (ADR-041).

The manifest is a deterministic derived artifact: it records which case ran, which
authoritative inputs produced it, the digests of every emitted artifact and the result of
every cross-component invariant check. The manifest binds the canonical digest file and
every payload artifact named by that file. Its own identity is content-addressed, so any
payload or manifest-byte change requires a different ``manifestId``.

The manifest never contains a filesystem path, a wall-clock timestamp, a random identifier
or any other environment-specific value.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from contracts._base import NonEmptyStr, NonNegInt, StrictModel

#: Version of the manifest contract itself.
PHASE1_MANIFEST_SCHEMA_VERSION = "1.1"

#: Version of the manifest-producing logic (bumped when check semantics change).
PHASE1_MANIFEST_VERSION = "phase1-verification-1.1.0"


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Phase1VerificationCheck(StrictModel):
    """One cross-component invariant result."""

    checkId: NonEmptyStr
    status: CheckStatus
    expected: str | None = None
    actual: str | None = None
    message: str | None = None

    @property
    def failed(self) -> bool:
        return self.status is CheckStatus.FAIL


class Phase1VerificationManifest(StrictModel):
    """Deterministic proof-of-run for one Phase 1 vertical slice."""

    schemaVersion: NonEmptyStr = PHASE1_MANIFEST_SCHEMA_VERSION
    manifestId: NonEmptyStr
    manifestVersion: NonEmptyStr
    caseId: NonEmptyStr
    caseVersion: NonEmptyStr
    scenarioVersion: NonEmptyStr
    scenarioDigest: NonEmptyStr
    analyticsPolicyDigest: NonEmptyStr
    runId: NonEmptyStr
    seed: int
    workoutDigest: NonEmptyStr
    sourceWorkoutDigest: str | None
    profileDigests: dict[str, str]
    selectedProfileId: NonEmptyStr
    selectedProfileVersion: NonEmptyStr
    replacementProfileId: str | None
    replacementProfileVersion: str | None
    compiledTimelineDigest: NonEmptyStr
    journalSha256: NonEmptyStr
    reportSha256: NonEmptyStr
    artifactDigests: dict[str, str]
    artifactDigestFileSha256: NonEmptyStr
    eventFirstSeq: NonNegInt
    eventLastSeq: NonNegInt
    eventCount: NonNegInt
    batchCount: NonNegInt
    liveReplayMatch: bool
    officialDistanceValid: bool
    clockInvariantsValid: bool
    profileInvariantsValid: bool
    reportValid: bool
    canonicalArtifactsValid: bool
    checks: tuple[Phase1VerificationCheck, ...]
    warnings: tuple[str, ...]
    allChecksPassed: bool
    runnerVersion: NonEmptyStr
    analyticsVersion: NonEmptyStr
    compilerVersion: NonEmptyStr
    replayVersion: NonEmptyStr


def encode_manifest(manifest: Phase1VerificationManifest) -> bytes:
    """Canonical UTF-8 JSON: sorted keys, compact separators, finite-only, LF only."""
    payload = manifest.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def decode_manifest(data: bytes) -> Phase1VerificationManifest:
    return Phase1VerificationManifest.model_validate(json.loads(data.decode("utf-8")))


def deterministic_manifest_id(manifest: Phase1VerificationManifest) -> str:
    """SHA-256 over the canonical manifest with only ``manifestId`` omitted."""
    payload = manifest.model_dump(mode="json", exclude_none=False)
    payload.pop("manifestId", None)
    identity = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def finalize_manifest(draft: Phase1VerificationManifest) -> Phase1VerificationManifest:
    """Stamp the content-addressed identity onto a draft manifest."""
    return draft.model_copy(update={"manifestId": deterministic_manifest_id(draft)})


def manifest_sha256(manifest: Phase1VerificationManifest) -> str:
    return hashlib.sha256(encode_manifest(manifest)).hexdigest()


__all__ = [
    "PHASE1_MANIFEST_SCHEMA_VERSION",
    "PHASE1_MANIFEST_VERSION",
    "CheckStatus",
    "Phase1VerificationCheck",
    "Phase1VerificationManifest",
    "decode_manifest",
    "deterministic_manifest_id",
    "encode_manifest",
    "finalize_manifest",
    "manifest_sha256",
]
