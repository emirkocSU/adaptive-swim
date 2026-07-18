"""Physiological target contracts (advisory only).

Heart rate is never a stand-alone reason to change pace, and ``hrControlMode`` is
``ADVISORY`` in Phase 1 (there is no live HR control mode). A single bad HR sample never
moves the ghost. HR may inform the planning model and the report; live it is a supporting
signal at most.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from contracts._base import StrictModel
from contracts.enums import EffortTargetType, HrControlMode


class PhysiologyTarget(StrictModel):
    """Optional physiological target attached to a workout or approved pace profile."""

    targetHrZone: Annotated[int, Field(ge=1, le=5)] | None = None
    maxHrPercentMin: Annotated[float, Field(ge=0, le=100)] | None = None
    maxHrPercentMax: Annotated[float, Field(ge=0, le=100)] | None = None
    rpeTarget: Annotated[float, Field(ge=0, le=10)] | None = None
    effortTargetType: EffortTargetType | None = None
    #: Phase 1 accepts only ADVISORY (there is no live HR control mode).
    hrControlMode: HrControlMode = HrControlMode.ADVISORY

    @model_validator(mode="after")
    def _check(self) -> PhysiologyTarget:
        lo, hi = self.maxHrPercentMin, self.maxHrPercentMax
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"maxHrPercentMin {lo} must be <= maxHrPercentMax {hi}")
        if self.hrControlMode is not HrControlMode.ADVISORY:
            raise ValueError("Phase 1 supports only hrControlMode=ADVISORY")
        return self
