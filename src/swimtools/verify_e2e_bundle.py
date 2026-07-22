"""Re-verify a Phase 1 e2e output bundle from its bytes alone (ADR-041).

The verifier trusts nothing but the files: it re-reads the journal through the real event
log, replays it, re-derives every recorded digest and identity, and cross-checks the
manifest, report and journal against each other. An unaccompanied byte change fails; a
coherent payload change requires a new digest chain and therefore a different manifestId.

    python -m swimtools.verify_e2e_bundle --bundle ./output
    python -m swimtools.verify_e2e_bundle --bundle ./e2e-all --recursive --format json

Typed exit codes:

``0`` valid · ``2`` invalid input (missing/unreadable/non-canonical) · ``3`` digest
mismatch · ``4`` semantic mismatch between artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from analytics.identity import deterministic_report_id, event_digest_sha256
from analytics.serialization import decode_session_report, encode_session_report
from e2e.errors import E2EBundleDigestError, E2EBundleInputError, E2EBundleSemanticError
from e2e.identity import deterministic_run_id
from e2e.manifest import (
    CheckStatus,
    Phase1VerificationManifest,
    decode_manifest,
    deterministic_manifest_id,
    encode_manifest,
)
from e2e.types import (
    BUNDLE_COMMAND_OUTCOMES_FILE,
    BUNDLE_JOURNAL_FILE,
    BUNDLE_MANIFEST_FILE,
    BUNDLE_OBSERVATIONS_FILE,
    BUNDLE_REPORT_FILE,
    BUNDLE_SHA256_FILE,
    REQUIRED_BUNDLE_FILES,
)
from persistence.codec import decode_batch
from persistence.jsonl_event_log import JsonlSessionEventLog

EXIT_VALID = 0
EXIT_INVALID_INPUT = 2
EXIT_DIGEST_MISMATCH = 3
EXIT_SEMANTIC_MISMATCH = 4


@dataclass
class BundleVerification:
    bundlePath: str
    valid: bool = False
    caseId: str | None = None
    manifestId: str | None = None
    runId: str | None = None
    reportId: str | None = None
    checkedFiles: tuple[str, ...] = ()
    errors: list[str] = field(default_factory=list)
    exitCode: int = EXIT_VALID

    def as_dict(self) -> dict[str, object]:
        return {
            "bundlePath": self.bundlePath,
            "valid": self.valid,
            "caseId": self.caseId,
            "manifestId": self.manifestId,
            "runId": self.runId,
            "reportId": self.reportId,
            "checkedFiles": list(self.checkedFiles),
            "errors": list(self.errors),
            "exitCode": self.exitCode,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_digest_file(data: bytes) -> dict[str, str]:
    if b"\r\n" in data or not data.endswith(b"\n"):
        raise E2EBundleInputError("artifact-sha256.txt must use LF and end with one LF")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise E2EBundleInputError("artifact-sha256.txt is not UTF-8") from exc
    lines = text.splitlines()
    if not lines:
        raise E2EBundleInputError("artifact-sha256.txt is empty")
    digests: dict[str, str] = {}
    names: list[str] = []
    for line in lines:
        parts = line.split("  ")
        if len(parts) != 2:
            raise E2EBundleInputError(f"malformed digest line: {line!r}")
        digest, name = parts
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise E2EBundleInputError(f"malformed sha256 in digest line: {line!r}")
        if not name or name in digests:
            raise E2EBundleInputError(f"duplicate/empty digest member: {name!r}")
        digests[name] = digest
        names.append(name)
    if names != sorted(names):
        raise E2EBundleInputError("artifact-sha256.txt members must be sorted")
    canonical = ("\n".join(f"{digests[name]}  {name}" for name in names) + "\n").encode("utf-8")
    if canonical != data:
        raise E2EBundleInputError("artifact-sha256.txt is not canonical")
    return digests


def _require_canonical_json(data: bytes, label: str) -> object:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise E2EBundleInputError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if data not in (canonical, canonical + b"\n"):
        raise E2EBundleInputError(f"{label} is valid JSON but not canonical")
    return value


def verify_bundle(bundle: Path) -> BundleVerification:
    """Verify one bundle directory. Never raises; failures are reported in the result."""
    result = BundleVerification(bundlePath=bundle.name)
    try:
        if not bundle.is_dir():
            raise E2EBundleInputError(f"bundle directory not found: {bundle}")
        missing = [name for name in REQUIRED_BUNDLE_FILES if not (bundle / name).is_file()]
        if missing:
            raise E2EBundleInputError(f"missing required bundle files: {missing}")

        manifest_bytes = (bundle / BUNDLE_MANIFEST_FILE).read_bytes()
        report_bytes = (bundle / BUNDLE_REPORT_FILE).read_bytes()
        journal_bytes = (bundle / BUNDLE_JOURNAL_FILE).read_bytes()
        outcomes_bytes = (bundle / BUNDLE_COMMAND_OUTCOMES_FILE).read_bytes()
        digest_bytes = (bundle / BUNDLE_SHA256_FILE).read_bytes()

        # ---- canonical form -----------------------------------------------------------
        _require_canonical_json(manifest_bytes, BUNDLE_MANIFEST_FILE)
        _require_canonical_json(report_bytes, BUNDLE_REPORT_FILE)
        _require_canonical_json(outcomes_bytes, BUNDLE_COMMAND_OUTCOMES_FILE)
        if b"\r\n" in journal_bytes or b"\r\n" in manifest_bytes:
            raise E2EBundleInputError("bundle artifacts must use LF line endings")
        journal_lines = [line for line in journal_bytes.split(b"\n") if line.strip()]
        if not journal_lines:
            raise E2EBundleInputError("journal is empty")
        for index, line in enumerate(journal_lines):
            _require_canonical_json(line, f"{BUNDLE_JOURNAL_FILE} line {index + 1}")

        try:
            manifest: Phase1VerificationManifest = decode_manifest(manifest_bytes)
        except ValueError as exc:
            raise E2EBundleInputError(f"manifest does not satisfy its contract: {exc}") from exc
        result.caseId = manifest.caseId
        result.manifestId = manifest.manifestId
        result.runId = manifest.runId
        if encode_manifest(manifest) != manifest_bytes:
            raise E2EBundleInputError("manifest bytes are not the canonical encoding")

        try:
            report = decode_session_report(report_bytes)
        except ValueError as exc:
            raise E2EBundleInputError(f"report does not satisfy its contract: {exc}") from exc
        result.reportId = report.reportId
        if encode_session_report(report) != report_bytes:
            raise E2EBundleInputError("report bytes are not the canonical encoding")

        # ---- exact bundle membership and recorded digests ------------------------------
        observations_path = bundle / BUNDLE_OBSERVATIONS_FILE
        payload_members: dict[str, bytes] = {
            BUNDLE_JOURNAL_FILE: journal_bytes,
            BUNDLE_REPORT_FILE: report_bytes,
            BUNDLE_COMMAND_OUTCOMES_FILE: outcomes_bytes,
        }
        if observations_path.is_file():
            observation_bytes = observations_path.read_bytes()
            payload_members[BUNDLE_OBSERVATIONS_FILE] = observation_bytes
            if b"\r\n" in observation_bytes:
                raise E2EBundleInputError("observations.jsonl must use LF line endings")
            observation_lines = [line for line in observation_bytes.split(b"\n") if line.strip()]
            for index, line in enumerate(observation_lines):
                _require_canonical_json(line, f"{BUNDLE_OBSERVATIONS_FILE} line {index + 1}")

        expected_names = set(payload_members) | {BUNDLE_MANIFEST_FILE, BUNDLE_SHA256_FILE}
        actual_names = {item.name for item in bundle.iterdir()}
        if actual_names != expected_names:
            raise E2EBundleInputError(
                f"bundle members {sorted(actual_names)} != expected {sorted(expected_names)}"
            )
        if any(not item.is_file() for item in bundle.iterdir()):
            raise E2EBundleInputError("bundle may contain files only")

        recorded = _parse_digest_file(digest_bytes)
        if set(recorded) != set(payload_members):
            raise E2EBundleInputError(
                f"digest file lists {sorted(recorded)}, payload holds {sorted(payload_members)}"
            )
        measured_payload_digests = {
            name: _sha256(data) for name, data in sorted(payload_members.items())
        }
        for name, measured in measured_payload_digests.items():
            if recorded[name] != measured:
                raise E2EBundleDigestError(
                    f"{name}: recorded {recorded[name]}, measured {measured}"
                )
        if manifest.artifactDigests != measured_payload_digests:
            raise E2EBundleDigestError(
                "manifest artifactDigests do not match the measured payload bytes"
            )
        if manifest.artifactDigestFileSha256 != _sha256(digest_bytes):
            raise E2EBundleDigestError(
                "manifest artifactDigestFileSha256 does not match artifact-sha256.txt"
            )
        if manifest.journalSha256 != measured_payload_digests[BUNDLE_JOURNAL_FILE]:
            raise E2EBundleDigestError("manifest journalSha256 does not match journal.jsonl")
        if manifest.reportSha256 != measured_payload_digests[BUNDLE_REPORT_FILE]:
            raise E2EBundleDigestError("manifest reportSha256 does not match session-report.json")
        if manifest.manifestId != deterministic_manifest_id(manifest):
            raise E2EBundleDigestError("manifestId is not the content-addressed identity")
        if report.reportId != deterministic_report_id(report):
            raise E2EBundleDigestError("reportId is not the content-addressed identity")

        selected_key = f"{manifest.selectedProfileId}:{manifest.selectedProfileVersion}"
        if selected_key not in manifest.profileDigests:
            raise E2EBundleSemanticError(
                f"selected profile identity {selected_key!r} is absent from profileDigests"
            )
        replacement_pair = (manifest.replacementProfileId, manifest.replacementProfileVersion)
        if (replacement_pair[0] is None) != (replacement_pair[1] is None):
            raise E2EBundleSemanticError(
                "replacement profile id/version must both be present or both be absent"
            )
        if replacement_pair[0] is not None:
            replacement_key = f"{replacement_pair[0]}:{replacement_pair[1]}"
            if replacement_key not in manifest.profileDigests:
                raise E2EBundleSemanticError(
                    f"replacement profile identity {replacement_key!r} is absent from profileDigests"
                )
        expected_run_id = deterministic_run_id(
            case_id=manifest.caseId,
            case_version=manifest.caseVersion,
            seed=manifest.seed,
            workout_digest=manifest.workoutDigest,
            source_workout_digest=manifest.sourceWorkoutDigest,
            profile_digests=manifest.profileDigests,
            selected_profile_id=manifest.selectedProfileId,
            selected_profile_version=manifest.selectedProfileVersion,
            replacement_profile_id=manifest.replacementProfileId,
            replacement_profile_version=manifest.replacementProfileVersion,
            scenario_version=manifest.scenarioVersion,
            scenario_digest=manifest.scenarioDigest,
            analytics_policy_digest=manifest.analyticsPolicyDigest,
            runner_version=manifest.runnerVersion,
        )
        if manifest.runId != expected_run_id:
            raise E2EBundleDigestError("runId is not the deterministic input identity")
        result.checkedFiles = tuple(sorted(expected_names))

        # ---- semantic agreement --------------------------------------------------------
        session_id = decode_batch(journal_lines[0]).sessionId
        events = JsonlSessionEventLog(bundle / BUNDLE_JOURNAL_FILE, session_id).read_all().events
        batches = [decode_batch(line) for line in journal_lines]
        if manifest.eventCount != len(events):
            raise E2EBundleSemanticError(
                f"manifest eventCount {manifest.eventCount} != journal {len(events)}"
            )
        if manifest.batchCount != len(batches):
            raise E2EBundleSemanticError(
                f"manifest batchCount {manifest.batchCount} != journal lines {len(batches)}"
            )
        if manifest.eventFirstSeq != events[0].seq or manifest.eventLastSeq != events[-1].seq:
            raise E2EBundleSemanticError("manifest event sequence bounds disagree with the journal")
        if report.sessionId != session_id:
            raise E2EBundleSemanticError("report sessionId disagrees with the journal")
        if report.createdFromLastSeq != events[-1].seq:
            raise E2EBundleSemanticError("report createdFromLastSeq disagrees with the journal")
        digest = event_digest_sha256(events)
        if report.provenance.eventDigestSha256 != digest:
            raise E2EBundleSemanticError("report event digest disagrees with the journal")
        if report.provenance.simulationRunId != manifest.runId:
            raise E2EBundleSemanticError("report simulationRunId disagrees with manifest runId")
        if not manifest.allChecksPassed:
            failed = [
                check.checkId for check in manifest.checks if check.status is CheckStatus.FAIL
            ]
            raise E2EBundleSemanticError(f"manifest records failed checks: {failed}")
        recorded_failures = [
            check.checkId for check in manifest.checks if check.status is CheckStatus.FAIL
        ]
        if recorded_failures:
            raise E2EBundleSemanticError(f"manifest contains failed checks: {recorded_failures}")

        outcomes = json.loads(outcomes_bytes.decode("utf-8"))
        if not isinstance(outcomes, list):
            raise E2EBundleInputError("command-outcomes.json must be a JSON array")
        persisted_command_ids = {batch.clientCommandId for batch in batches}
        applied = {
            item["clientCommandId"]
            for item in outcomes
            if isinstance(item, dict) and item.get("outcome") == "APPLIED"
        }
        if not applied <= persisted_command_ids:
            raise E2EBundleSemanticError(
                "an applied command outcome has no persisted journal batch"
            )
        rejected_with_events = [
            item["clientCommandId"]
            for item in outcomes
            if isinstance(item, dict)
            and item.get("outcome") == "REJECTED"
            and item.get("eventCount")
        ]
        if rejected_with_events:
            raise E2EBundleSemanticError(
                f"rejected commands recorded events: {rejected_with_events}"
            )

        result.valid = True
        result.exitCode = EXIT_VALID
    except E2EBundleInputError as exc:
        result.errors.append(str(exc))
        result.exitCode = EXIT_INVALID_INPUT
    except E2EBundleDigestError as exc:
        result.errors.append(str(exc))
        result.exitCode = EXIT_DIGEST_MISMATCH
    except E2EBundleSemanticError as exc:
        result.errors.append(str(exc))
        result.exitCode = EXIT_SEMANTIC_MISMATCH
    return result


def _bundle_directories(root: Path, recursive: bool) -> list[Path]:
    if (root / BUNDLE_MANIFEST_FILE).is_file():
        return [root]
    if not recursive and not root.is_dir():
        return [root]
    children = sorted(child for child in root.iterdir() if (child / BUNDLE_MANIFEST_FILE).is_file())
    return children or [root]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="swimtools.verify_e2e_bundle",
        description="Verify a Phase 1 e2e output bundle from its bytes",
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="treat --bundle as a directory of bundles (default when no manifest is present)",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    root = Path(args.bundle)
    if not root.exists():
        print(f"bundle not found: {root}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    results = [verify_bundle(directory) for directory in _bundle_directories(root, args.recursive)]
    if args.format == "json":
        print(json.dumps([item.as_dict() for item in results], ensure_ascii=False, indent=2))
    else:
        for item in results:
            status = "VALID" if item.valid else f"INVALID(exit={item.exitCode})"
            print(f"[{status}] {item.bundlePath} case={item.caseId} manifest={item.manifestId}")
            for error in item.errors:
                print(f"  error: {error}")
    worst = EXIT_VALID
    for item in results:
        if item.exitCode != EXIT_VALID:
            worst = max(worst, item.exitCode)
    return worst


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
