"""Phase 1 full vertical-slice verification (ADR-041).

This layer owns no domain logic. It orders the real components — contracts, ``swimcore``,
``persistence``, ``simulator`` and ``analytics`` — into one authoritative Phase 1 run, checks
the cross-component invariants and emits a canonical, deterministic verification bundle.

``swimcore``, ``contracts``, ``analytics`` and ``persistence`` must never import this package.
"""

from e2e.cases import ALL_CASES, CASE_BY_ID, REQUIRED_CASE_IDS, build_all_cases
from e2e.errors import (
    E2EBundleDigestError,
    E2EBundleInputError,
    E2EBundleSemanticError,
    E2ECaseError,
    E2EError,
    E2EVerificationError,
)
from e2e.manifest import (
    CheckStatus,
    Phase1VerificationCheck,
    Phase1VerificationManifest,
    decode_manifest,
    deterministic_manifest_id,
    encode_manifest,
    manifest_sha256,
)
from e2e.runner import (
    REPLAY_VERSION,
    deterministic_run_id,
    require_all_checks_passed,
    run_phase1_vertical_slice,
)
from e2e.types import (
    E2E_RUNNER_VERSION,
    REQUIRED_BUNDLE_FILES,
    E2EAnalyticsPolicy,
    Phase1E2ECase,
    Phase1E2EResult,
    Phase1ExpectedOutcome,
)

__all__ = [
    "ALL_CASES",
    "CASE_BY_ID",
    "E2E_RUNNER_VERSION",
    "REPLAY_VERSION",
    "REQUIRED_BUNDLE_FILES",
    "REQUIRED_CASE_IDS",
    "CheckStatus",
    "E2EAnalyticsPolicy",
    "E2EBundleDigestError",
    "E2EBundleInputError",
    "E2EBundleSemanticError",
    "E2ECaseError",
    "E2EError",
    "E2EVerificationError",
    "Phase1E2ECase",
    "Phase1E2EResult",
    "Phase1ExpectedOutcome",
    "Phase1VerificationCheck",
    "Phase1VerificationManifest",
    "build_all_cases",
    "decode_manifest",
    "deterministic_manifest_id",
    "deterministic_run_id",
    "encode_manifest",
    "manifest_sha256",
    "require_all_checks_passed",
    "run_phase1_vertical_slice",
]
