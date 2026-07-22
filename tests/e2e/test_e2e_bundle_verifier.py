"""The bundle verifier re-proves a bundle from its bytes alone (ADR-041 §11)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from e2e.types import (
    BUNDLE_COMMAND_OUTCOMES_FILE,
    BUNDLE_JOURNAL_FILE,
    BUNDLE_MANIFEST_FILE,
    BUNDLE_OBSERVATIONS_FILE,
    BUNDLE_REPORT_FILE,
    BUNDLE_SHA256_FILE,
    Phase1E2EResult,
)
from swimtools.verify_e2e_bundle import (
    EXIT_DIGEST_MISMATCH,
    EXIT_INVALID_INPUT,
    EXIT_SEMANTIC_MISMATCH,
    EXIT_VALID,
    verify_bundle,
)

CASE = "long-stop-and-reconciliation"


@pytest.fixture
def bundle(run_case: Callable[..., Phase1E2EResult], tmp_path: Path) -> Path:
    result = run_case(CASE)
    target = tmp_path / "bundle"
    shutil.copytree(result.bundleDirectory, target)
    return target


def _rewrite_canonical(path: Path, mutate: Callable[[dict], None]) -> None:
    payload = json.loads(path.read_bytes())
    mutate(payload)
    path.write_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    )


def _reidentify_manifest(path: Path) -> None:
    import hashlib

    payload = json.loads(path.read_bytes())
    payload["manifestId"] = "PENDING"
    identity_payload = dict(payload)
    identity_payload.pop("manifestId")
    material = json.dumps(
        identity_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload["manifestId"] = hashlib.sha256(material).hexdigest()
    path.write_bytes(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _rewrite_payload_digest_file(bundle: Path) -> None:
    import hashlib

    digest_path = bundle / BUNDLE_SHA256_FILE
    names = [
        line.split("  ", 1)[1]
        for line in digest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lines = [
        f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}"
        for name in sorted(names)
    ]
    digest_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def test_a_pristine_bundle_verifies(bundle: Path) -> None:
    result = verify_bundle(bundle)
    assert result.valid
    assert result.exitCode == EXIT_VALID
    assert result.errors == []
    assert result.caseId == CASE
    assert set(result.checkedFiles) == {
        BUNDLE_JOURNAL_FILE,
        BUNDLE_REPORT_FILE,
        BUNDLE_COMMAND_OUTCOMES_FILE,
        BUNDLE_MANIFEST_FILE,
        BUNDLE_SHA256_FILE,
    }


@pytest.mark.parametrize(
    "name",
    [
        BUNDLE_MANIFEST_FILE,
        BUNDLE_JOURNAL_FILE,
        BUNDLE_REPORT_FILE,
        BUNDLE_COMMAND_OUTCOMES_FILE,
        BUNDLE_SHA256_FILE,
    ],
)
def test_a_missing_required_file_is_invalid_input(bundle: Path, name: str) -> None:
    (bundle / name).unlink()
    result = verify_bundle(bundle)
    assert result.exitCode == EXIT_INVALID_INPUT
    assert not result.valid


def test_one_changed_byte_in_the_report_fails(bundle: Path) -> None:
    _rewrite_canonical(bundle / BUNDLE_REPORT_FILE, lambda payload: payload.update(notes="x"))
    result = verify_bundle(bundle)
    assert result.exitCode == EXIT_DIGEST_MISMATCH


def test_one_changed_byte_in_the_journal_fails(bundle: Path) -> None:
    path = bundle / BUNDLE_JOURNAL_FILE
    lines = path.read_bytes().split(b"\n")
    lines[0] = lines[0].replace(b'"eventCount":2', b'"eventCount":3')
    path.write_bytes(b"\n".join(lines))
    result = verify_bundle(bundle)
    assert result.exitCode in {EXIT_INVALID_INPUT, EXIT_DIGEST_MISMATCH}
    assert not result.valid


def test_pretty_printed_json_is_rejected(bundle: Path) -> None:
    path = bundle / BUNDLE_MANIFEST_FILE
    payload = json.loads(path.read_bytes())
    path.write_bytes(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
    result = verify_bundle(bundle)
    assert result.exitCode == EXIT_INVALID_INPUT
    assert any("canonical" in error for error in result.errors)


def test_a_tampered_digest_file_fails(bundle: Path) -> None:
    path = bundle / BUNDLE_SHA256_FILE
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("a", "b", 1), encoding="utf-8")
    result = verify_bundle(bundle)
    assert result.exitCode in {EXIT_INVALID_INPUT, EXIT_DIGEST_MISMATCH}


def test_a_manifest_that_disagrees_with_the_journal_fails(bundle: Path) -> None:
    def mutate(payload: dict) -> None:
        payload["eventCount"] = payload["eventCount"] + 1
        payload.pop("manifestId")
        payload["manifestId"] = "0" * 64

    _rewrite_canonical(bundle / BUNDLE_MANIFEST_FILE, mutate)
    # keep the recorded digest consistent so the semantic layer is reached
    digest_path = bundle / BUNDLE_SHA256_FILE
    import hashlib

    lines = []
    for line in digest_path.read_text(encoding="utf-8").splitlines():
        _digest, name = line.split("  ")
        lines.append(f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}")
    digest_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    result = verify_bundle(bundle)
    assert result.exitCode in {EXIT_DIGEST_MISMATCH, EXIT_SEMANTIC_MISMATCH}


def test_a_manifest_recording_a_failed_check_is_semantically_rejected(bundle: Path) -> None:
    import hashlib

    def mutate(payload: dict) -> None:
        payload["checks"][0]["status"] = "FAIL"

    _rewrite_canonical(bundle / BUNDLE_MANIFEST_FILE, mutate)
    raw = json.loads((bundle / BUNDLE_MANIFEST_FILE).read_bytes())
    raw["manifestId"] = "PENDING"
    payload = dict(raw)
    payload.pop("manifestId")
    identity = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    raw["manifestId"] = hashlib.sha256(identity).hexdigest()
    (bundle / BUNDLE_MANIFEST_FILE).write_bytes(
        json.dumps(
            raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    )
    lines = []
    for line in (bundle / BUNDLE_SHA256_FILE).read_text(encoding="utf-8").splitlines():
        _digest, name = line.split("  ")
        lines.append(f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}")
    (bundle / BUNDLE_SHA256_FILE).write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    result = verify_bundle(bundle)
    assert result.exitCode == EXIT_SEMANTIC_MISMATCH


def test_a_missing_bundle_directory_is_invalid_input(tmp_path: Path) -> None:
    result = verify_bundle(tmp_path / "does-not-exist")
    assert result.exitCode == EXIT_INVALID_INPUT


def test_recomputed_run_id_is_required(bundle: Path) -> None:
    manifest_path = bundle / BUNDLE_MANIFEST_FILE
    _rewrite_canonical(
        manifest_path,
        lambda payload: payload.update(runId="f" * 64),
    )
    _reidentify_manifest(manifest_path)
    result = verify_bundle(bundle)
    assert result.exitCode == EXIT_DIGEST_MISMATCH
    assert any("runId" in error for error in result.errors)


def test_manifest_binds_outcomes_and_observations(
    run_case: Callable[..., Phase1E2EResult], tmp_path: Path
) -> None:
    source = run_case("unreliable-observation-report").bundleDirectory

    outcomes_bundle = tmp_path / "outcomes"
    shutil.copytree(source, outcomes_bundle)
    outcomes_path = outcomes_bundle / BUNDLE_COMMAND_OUTCOMES_FILE
    outcomes = json.loads(outcomes_path.read_bytes())
    outcomes.append(
        {
            "atMs": 0,
            "clientCommandId": "tampered",
            "commandType": "Tampered",
            "error": None,
            "eventCount": 0,
            "outcome": "REJECTED",
        }
    )
    outcomes_path.write_bytes(
        json.dumps(
            outcomes,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    _rewrite_payload_digest_file(outcomes_bundle)
    outcomes_result = verify_bundle(outcomes_bundle)
    assert outcomes_result.exitCode == EXIT_DIGEST_MISMATCH

    observations_bundle = tmp_path / "observations"
    shutil.copytree(source, observations_bundle)
    observations_path = observations_bundle / BUNDLE_OBSERVATIONS_FILE
    lines = [line for line in observations_path.read_bytes().split(b"\n") if line]
    first = json.loads(lines[0])
    first["quality"] = "LOW"
    lines[0] = json.dumps(
        first,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    observations_path.write_bytes(b"\n".join(lines) + b"\n")
    _rewrite_payload_digest_file(observations_bundle)
    observations_result = verify_bundle(observations_bundle)
    assert observations_result.exitCode == EXIT_DIGEST_MISMATCH
