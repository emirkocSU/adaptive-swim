"""Committed full golden bundles are the Phase 1 release regression contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from e2e.types import (
    BUNDLE_COMMAND_OUTCOMES_FILE,
    BUNDLE_JOURNAL_FILE,
    BUNDLE_MANIFEST_FILE,
    BUNDLE_REPORT_FILE,
    BUNDLE_SHA256_FILE,
    Phase1E2EResult,
)
from swimtools.verify_e2e_bundle import EXIT_VALID, verify_bundle

GOLDEN_DIR = Path(__file__).parent / "goldens"

#: golden directory -> case id
GOLDEN_CASES = {
    "normal-continuous": "normal-continuous-completion",
    "legacy-profile": "legacy-profile-compatibility",
    "long-stop": "long-stop-and-reconciliation",
    "coach-reset": "coach-profile-reset",
    "dataset-evidence": "dataset-evidence-provenance",
}

_MEMBERS = (
    BUNDLE_JOURNAL_FILE,
    BUNDLE_REPORT_FILE,
    BUNDLE_COMMAND_OUTCOMES_FILE,
    BUNDLE_SHA256_FILE,
    BUNDLE_MANIFEST_FILE,
)
_PAYLOAD_MEMBERS = (
    BUNDLE_COMMAND_OUTCOMES_FILE,
    BUNDLE_JOURNAL_FILE,
    BUNDLE_REPORT_FILE,
)


@pytest.mark.parametrize("golden", sorted(GOLDEN_CASES))
def test_golden_directory_is_complete(golden: str) -> None:
    directory = GOLDEN_DIR / golden
    assert directory.is_dir()
    assert sorted(path.name for path in directory.iterdir()) == sorted(_MEMBERS)


@pytest.mark.parametrize("golden,case_id", sorted(GOLDEN_CASES.items()))
def test_golden_bytes_are_reproduced_exactly(
    golden: str, case_id: str, run_case: Callable[..., Phase1E2EResult]
) -> None:
    result = run_case(case_id)
    directory = GOLDEN_DIR / golden
    for name in _MEMBERS:
        assert (result.bundleDirectory / name).read_bytes() == (directory / name).read_bytes(), (
            f"{golden}/{name} drifted"
        )


@pytest.mark.parametrize("golden", sorted(GOLDEN_CASES))
def test_golden_digest_file_matches_every_payload_and_manifest(golden: str) -> None:
    directory = GOLDEN_DIR / golden
    manifest = json.loads((directory / BUNDLE_MANIFEST_FILE).read_bytes())
    digest_bytes = (directory / BUNDLE_SHA256_FILE).read_bytes()
    recorded: dict[str, str] = {}
    for line in digest_bytes.decode("utf-8").splitlines():
        digest, name = line.split("  ")
        recorded[name] = digest

    assert set(recorded) == set(_PAYLOAD_MEMBERS)
    measured = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in _PAYLOAD_MEMBERS
    }
    assert recorded == measured
    assert manifest["artifactDigests"] == measured
    assert manifest["artifactDigestFileSha256"] == hashlib.sha256(digest_bytes).hexdigest()


@pytest.mark.parametrize("golden", sorted(GOLDEN_CASES))
def test_golden_bundle_verifies_from_its_own_bytes(golden: str) -> None:
    verification = verify_bundle(GOLDEN_DIR / golden)
    assert verification.exitCode == EXIT_VALID
    assert verification.valid
    assert verification.caseId == GOLDEN_CASES[golden]


@pytest.mark.parametrize("golden", sorted(GOLDEN_CASES))
def test_goldens_hold_no_environment_specific_content(golden: str) -> None:
    directory = GOLDEN_DIR / golden
    for name in _MEMBERS:
        raw = (directory / name).read_bytes()
        assert b"\r\n" not in raw, f"{golden}/{name} must use LF endings"
        text = raw.decode("utf-8")
        for forbidden in ("/tmp", "/home", "C:\\", "file://", "phase1-e2e-"):
            assert forbidden not in text, f"{golden}/{name} leaks {forbidden}"
