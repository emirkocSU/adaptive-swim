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

# --------------------------------------------------------------------------- finite types
# Pydantic's plain float comparisons treat +inf as "> 0", so a bare ``gt=0`` constraint
# accepts positive infinity. The finite variants below set ``allow_inf_nan=False`` so NaN,
# +inf and -inf are rejected at the contract boundary (Commit 8 correction §2.8). Python
# runtime validation is authoritative; the generated JSON Schema reflects the numeric range
# where the dialect can express it (JSON itself cannot encode inf/NaN).

#: Finite float (rejects NaN / +inf / -inf).
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]

#: Strictly positive finite float.
PosFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]

#: Non-negative finite float.
NonNegFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]

#: Finite ratio / probability in the closed unit interval.
UnitFiniteRatio = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]

#: Ratio / probability in the closed unit interval.
UnitRatio = Annotated[float, Field(ge=0, le=1)]

#: Strictly positive integer (counts that may not be zero).
PosInt = Annotated[int, Field(ge=1)]

#: Session-monotonic sequence number (>= 1).
SeqInt = Annotated[int, Field(ge=1)]

#: Non-empty identifier / free-text-required string.
NonEmptyStr = Annotated[str, Field(min_length=1)]
