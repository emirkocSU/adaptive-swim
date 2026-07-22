"""Repeat / split forecasting contracts (ADR-039, contract level only).

No forecasting model exists in this repository; these types fix the *interface* so a later
Phase 5C forecasting head cannot blur the line between a coach target and a model forecast:

- ``coachTargetTimeSec`` is the coach's target. A forecast result NEVER mutates it.
- ``predictedNextRepeatTimeSec`` / ``predictedNextSplitTimeSec`` are model outputs.
- ``suggestionMode`` says how the forecast may reach the coach; under out-of-distribution
  or domain-extrapolation conditions ``BOUNDED_AUTO`` is forbidden — only suggest-only or
  the safe baseline remain (plan §9).

``swimcore`` MUST NOT import this module (import-linter enforced): forecasts never reach
the deterministic live runtime directly.
"""

from __future__ import annotations

from pydantic import model_validator

from contracts._base import (
    NonEmptyStr,
    NonNegInt,
    PosFiniteFloat,
    StrictModel,
    UnitFiniteRatio,
)
from contracts.enums import ForecastSuggestionMode, Stroke


class RepeatForecastContext(StrictModel):
    """Inputs available when forecasting the next repeat of a training set."""

    athleteRef: NonEmptyStr
    stroke: Stroke
    poolLengthM: int
    repeatDistanceM: PosFiniteFloat
    repeatIndex: NonNegInt
    completedRepeatTimesSec: tuple[PosFiniteFloat, ...] = ()
    restIntervalSec: PosFiniteFloat | None = None
    coachTargetTimeSec: PosFiniteFloat | None = None
    targetIntensityRatio: UnitFiniteRatio | None = None
    trainingContextCompleteness: UnitFiniteRatio | None = None
    domainExtrapolationFlag: bool = False
    oodFlag: bool = False

    @model_validator(mode="after")
    def _check(self) -> RepeatForecastContext:
        if self.poolLengthM not in (25, 50):
            raise ValueError(f"poolLengthM must be 25 or 50, got {self.poolLengthM}")
        return self


class RepeatForecastOutput(StrictModel):
    """One forecast for the next repeat. Never a target; never mutates the coach target."""

    #: Echo of the coach target this forecast was made against (unchanged by the model).
    coachTargetTimeSec: PosFiniteFloat | None = None
    predictedNextRepeatTimeSec: PosFiniteFloat
    predictedNextSplitTimeSec: PosFiniteFloat | None = None
    uncertaintyP10Sec: PosFiniteFloat | None = None
    uncertaintyP50Sec: PosFiniteFloat | None = None
    uncertaintyP90Sec: PosFiniteFloat | None = None
    #: Probability the coach target is missed, if a target was given.
    targetMissRisk: UnitFiniteRatio | None = None
    suggestionMode: ForecastSuggestionMode
    modelVersion: NonEmptyStr
    baselineVersion: str | None = None
    domainExtrapolationFlag: bool = False
    oodFlag: bool = False

    @model_validator(mode="after")
    def _check(self) -> RepeatForecastOutput:
        if (self.oodFlag or self.domainExtrapolationFlag) and (
            self.suggestionMode is ForecastSuggestionMode.BOUNDED_AUTO
        ):
            raise ValueError(
                "BOUNDED_AUTO is forbidden under OOD / domain extrapolation; use "
                "SUGGEST_ONLY or SAFE_BASELINE"
            )
        if self.targetMissRisk is not None and self.coachTargetTimeSec is None:
            raise ValueError("targetMissRisk requires a coachTargetTimeSec to be given")
        return self


__all__ = ["RepeatForecastContext", "RepeatForecastOutput"]
