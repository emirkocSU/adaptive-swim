"""Shared strict base model, reusable constrained types, and tolerance helpers.

All contract models forbid extra fields so that the generated JSON Schema carries
``additionalProperties: false`` (which lets structural golden validation reject unknown
keys) without any custom keyword.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

#: Absolute tolerance for cross-field floating-point equality checks.
FLOAT_TOLERANCE: float = 1e-6


def approx_equal(a: float, b: float, tol: float = FLOAT_TOLERANCE) -> bool:
    return abs(a - b) <= tol


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- constrained types
#: Pace in seconds per 100 m. Smaller = faster. Locked domain range.
PaceValue = Annotated[float, Field(gt=30, le=300)]

#: Non-negative integer (timestamps in ms, indices, counts).
NonNegInt = Annotated[int, Field(ge=0)]

#: Non-negative float (durations in seconds, etc.).
NonNegFloat = Annotated[float, Field(ge=0)]

#: Strictly positive float.
PosFloat = Annotated[float, Field(gt=0)]

#: Ratio / probability in the closed unit interval.
UnitRatio = Annotated[float, Field(ge=0, le=1)]

#: Session-monotonic sequence number (>= 1).
SeqInt = Annotated[int, Field(ge=1)]

#: Non-empty identifier / free-text-required string.
NonEmptyStr = Annotated[str, Field(min_length=1)]
