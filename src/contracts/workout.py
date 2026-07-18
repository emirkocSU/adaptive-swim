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

from pydantic import Field, model_validator

from contracts._base import NonNegFloat, NonNegInt, PaceValue, PosFloat, StrictModel
from contracts.enums import (
    AdaptationMode,
    AdaptationSource,
    PaceMode,
    SetLabel,
    StartMode,
    Stroke,
    WorkoutGoal,
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
    #: Workout 1.1: optional block-level start-mode override.
    startMode: StartMode | None = None


class WorkoutTemplateVersion(StrictModel):
    schemaVersion: Literal["1.0"]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    poolLengthM: Literal[25, 50]
    stroke: Stroke
    blocks: Annotated[list[RepeatBlock], Field(min_length=1)]


#: Explicit 1.0 alias (the discriminated union references it by this name).
WorkoutTemplateV1_0 = WorkoutTemplateVersion


# --------------------------------------------------------------------------- Workout 1.1
class StartPolicy(StrictModel):
    """Mandatory in Workout 1.1: how starts default and whether overrides are allowed."""

    defaultMode: StartMode
    allowBlockOverride: bool = True
    allowRepeatOverride: bool = True


class RepeatExecutionOverride(StrictModel):
    """Per-repetition override for start mode / profile.

    ``blockIndex`` disambiguates repeats across blocks (two blocks may each have a
    ``repeatIndex=0``); ``repeatIndex`` is 0-based within that block.
    """

    blockIndex: NonNegInt = 0
    repeatIndex: NonNegInt
    startMode: StartMode | None = None
    paceProfileRef: str | None = None


class WorkoutTemplateV1_1(StrictModel):
    schemaVersion: Literal["1.1"]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    poolLengthM: Literal[25, 50]
    stroke: Stroke
    startPolicy: StartPolicy
    workoutGoal: WorkoutGoal
    blocks: Annotated[list[RepeatBlock], Field(min_length=1)]
    repeatOverrides: list[RepeatExecutionOverride] = Field(default_factory=list)
    #: Optional total-target hint used by planning; leg durations are authoritative.
    targetTotalTimeSec: PosFloat | None = None

    @model_validator(mode="after")
    def _check_overrides(self) -> WorkoutTemplateV1_1:
        seen: set[tuple[int, int]] = set()
        for ov in self.repeatOverrides:
            key = (ov.blockIndex, ov.repeatIndex)
            if key in seen:
                raise ValueError(
                    f"duplicate override for block {ov.blockIndex} repeat {ov.repeatIndex}"
                )
            seen.add(key)
            if not (0 <= ov.blockIndex < len(self.blocks)):
                raise ValueError(f"override blockIndex {ov.blockIndex} out of range")
            block = self.blocks[ov.blockIndex]
            if not (0 <= ov.repeatIndex < block.repetitions):
                raise ValueError(
                    f"override repeatIndex {ov.repeatIndex} out of range for block "
                    f"{ov.blockIndex} ({block.repetitions} repetitions)"
                )
            if not self.startPolicy.allowRepeatOverride and ov.startMode is not None:
                raise ValueError(
                    f"block {ov.blockIndex} repeat {ov.repeatIndex} sets startMode but "
                    "startPolicy.allowRepeatOverride is false"
                )
        for b, block in enumerate(self.blocks):
            if block.startMode is not None and not self.startPolicy.allowBlockOverride:
                raise ValueError(
                    f"block {b} sets startMode but startPolicy.allowBlockOverride is false"
                )
        return self


#: Discriminated union over ``schemaVersion``. Consumers that only handle the runtime pace
#: model still use ``WorkoutTemplateVersion`` (the 1.0 shape) after an explicit migration.
WorkoutTemplate = Annotated[
    WorkoutTemplateV1_0 | WorkoutTemplateV1_1,
    Field(discriminator="schemaVersion"),
]

#: Plain (non-annotated) union for internal function signatures that accept either version.
AnyWorkoutTemplate = WorkoutTemplateV1_0 | WorkoutTemplateV1_1
