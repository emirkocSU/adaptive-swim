"""Workout DSL contracts (Layer-1 structural model).

Only the structural shape lives here. Semantic rules (contiguous coverage, pool-length
multiples, pace direction) belong to the Commit 3 semantic validator, not to the JSON
Schema and not encoded as custom keywords.

Pace vocabulary is locked:
``fastestAllowedPaceSecPer100M <= targetPaceSecPer100M <= slowestAllowedPaceSecPer100M``
(sec/100m: smaller = faster). The legacy min/max/coach pace field names are never used
(see the banned-vocabulary test).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from contracts._base import NonNegFloat, PaceValue, PosFloat, StrictModel
from contracts.enums import (
    AdaptationMode,
    AdaptationSource,
    PaceMode,
    SetLabel,
    Stroke,
)


class PaceSegment(StrictModel):
    fromM: Annotated[float, Field(ge=0)]
    toM: Annotated[float, Field(gt=0)]
    mode: PaceMode
    targetPaceSecPer100M: PaceValue
    #: Required for controlled_start (slower-or-equal start, i.e. >= target); forbidden else.
    startPaceSecPer100M: PaceValue | None = None
    endPaceSecPer100M: PaceValue | None = None


# --- rest policy (plain union; no discriminator keyword in the schema) ---
class RestNone(StrictModel):
    type: Literal["none"]


class RestFixed(StrictModel):
    type: Literal["fixed"]
    restSec: NonNegFloat


class RestInterval(StrictModel):
    type: Literal["interval"]
    startIntervalSec: PosFloat


RestPolicy = RestNone | RestFixed | RestInterval


class AdaptationPolicy(StrictModel):
    mode: AdaptationMode
    adaptationSource: AdaptationSource = AdaptationSource.rule_based
    maxChangePercentPerLength: Annotated[float, Field(ge=0.1, le=5.0)] | None = None
    minModelConfidence: Annotated[float, Field(ge=0.5, le=0.99)] = 0.80
    fastestAllowedPaceSecPer100M: PaceValue | None = None
    slowestAllowedPaceSecPer100M: PaceValue | None = None


class FeedbackPolicy(StrictModel):
    showGhost: bool = True
    showGapAtWall: bool = True
    showContinuousGap: bool = False


# --- ghost source (plain union) ---
class GhostSourcePlan(StrictModel):
    type: Literal["plan"]


class GhostSourcePersonalBest(StrictModel):
    type: Literal["personal_best"]
    referenceSessionId: str


class GhostSourcePastSession(StrictModel):
    type: Literal["past_session"]
    referenceSessionId: str


class GhostSourceCoachBenchmark(StrictModel):
    type: Literal["coach_benchmark"]
    profileRef: str


GhostSource = (
    GhostSourcePlan | GhostSourcePersonalBest | GhostSourcePastSession | GhostSourceCoachBenchmark
)


class RepeatBlock(StrictModel):
    type: Literal["repeat"]
    label: SetLabel | None = None
    repetitions: Annotated[int, Field(ge=1, le=100)]
    distanceM: Annotated[int, Field(ge=25)]
    rest: RestPolicy
    segments: Annotated[list[PaceSegment], Field(min_length=1)]
    adaptation: AdaptationPolicy | None = None
    feedback: FeedbackPolicy | None = None
    ghostSource: GhostSource | None = None


class WorkoutTemplateVersion(StrictModel):
    schemaVersion: Literal["1.0"]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    poolLengthM: Literal[25, 50]
    stroke: Stroke
    blocks: Annotated[list[RepeatBlock], Field(min_length=1)]
