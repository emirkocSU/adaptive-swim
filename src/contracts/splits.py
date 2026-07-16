"""Split contracts.

``qualityFlag`` is a *measurement-quality* axis only. A StopPause never turns a split
``INVALID``; StopPause exclusion is carried on the length outcome, not here.
"""

from __future__ import annotations

from contracts._base import NonEmptyStr, NonNegInt, StrictModel
from contracts.enums import SplitQualityFlag, SplitSource, VerificationSource


class Split(StrictModel):
    sessionId: NonEmptyStr
    lengthIndex: NonNegInt
    wallTimestampMs: NonNegInt
    source: SplitSource
    qualityFlag: SplitQualityFlag
    mlEligible: bool
    researchEligible: bool
    verificationRef: str | None = None
    clientCommandId: str | None = None


class SplitVerification(StrictModel):
    splitId: NonEmptyStr
    verificationSource: VerificationSource
    verifiedWallTimestampMs: NonNegInt
    #: wallTimestampMs - verifiedWallTimestampMs (manual measurement error).
    manualErrorMs: int
    verifiedBy: NonEmptyStr
    notes: str | None = None
