"""Typed failures raised by the Phase 1 vertical-slice runner and bundle verifier.

The e2e layer owns no domain rules; these errors describe orchestration, verification and
artifact-integrity failures only.
"""

from __future__ import annotations


class E2EError(Exception):
    """Base class for Phase 1 end-to-end failures."""


class E2ECaseError(E2EError):
    """A case definition is incomplete or internally contradictory."""


class E2EVerificationError(E2EError):
    """A cross-component invariant failed during a vertical-slice run."""


class E2EBundleInputError(E2EError):
    """A bundle is unreadable, incomplete or not valid canonical JSON/JSONL."""


class E2EBundleDigestError(E2EError):
    """A recorded artifact digest does not match the artifact bytes."""


class E2EBundleSemanticError(E2EError):
    """Bundle artifacts are individually well-formed but disagree with each other."""


__all__ = [
    "E2EBundleDigestError",
    "E2EBundleInputError",
    "E2EBundleSemanticError",
    "E2ECaseError",
    "E2EError",
    "E2EVerificationError",
]
