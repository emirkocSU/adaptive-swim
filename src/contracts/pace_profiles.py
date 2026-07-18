"""Approved pace-profile contracts (ADR-034).

An ``ApprovedPaceProfile`` is the single authoritative plan input consumed by the live
deterministic runtime. It carries distance-specific legs whose durations sum *exactly* to
the target total time (tolerance ``FLOAT_TOLERANCE``); the core never silently normalizes.

Profile legs are NOT official wall splits. A leg may be a start/underwater phase (e.g.
0–15 m) that never becomes an official split; official splits come only from verified wall
boundaries (ADR-036).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from contracts._base import (
    FLOAT_TOLERANCE,
    NonEmptyStr,
    NonNegInt,
    PosFloat,
    StrictModel,
)
from contracts.enums import (
    PaceProfilePhase,
    PaceProfileSource,
    PaceProfileType,
    ProfileApprovalStatus,
    StartMode,
    Stroke,
    WorkoutGoal,
)
from contracts.physiology import PhysiologyTarget

#: Approval statuses that a live session may run.
LIVE_ELIGIBLE_APPROVAL_STATUSES: frozenset[ProfileApprovalStatus] = frozenset(
    {
        ProfileApprovalStatus.COACH_APPROVED,
        ProfileApprovalStatus.COACH_LOCKED,
        ProfileApprovalStatus.APPROVED_BY_EXPLICIT_DEFAULT_POLICY,
    }
)


class PaceProfileLeg(StrictModel):
    """One distance-specific leg of a profile. Not an official wall split."""

    legIndex: NonNegInt
    fromM: Annotated[float, Field(ge=0)]
    toM: PosFloat
    targetDurationSec: PosFloat
    phaseType: PaceProfilePhase

    @property
    def legDistanceM(self) -> float:
        return self.toM - self.fromM

    @property
    def paceSecPer100M(self) -> float:
        """Constant leg pace: ``targetDurationSec * 100 / legDistanceM``."""
        return self.targetDurationSec * 100.0 / self.legDistanceM


class ModelProfileMetadata(StrictModel):
    modelVersion: NonEmptyStr
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    generatedAtMs: NonNegInt | None = None
    generalModelVersion: str | None = None
    personalCalibrationVersion: str | None = None
    coachConstraintVersion: str | None = None
    profileGenerationId: str | None = None


class CoachProfileMetadata(StrictModel):
    authoredBy: NonEmptyStr
    editedLegIndices: list[NonNegInt] = Field(default_factory=list)
    notes: str | None = None


class ApprovedPaceProfile(StrictModel):
    """Authoritative live plan input. Legs must cover the distance and sum to the total."""

    profileId: NonEmptyStr
    profileVersion: NonEmptyStr
    source: PaceProfileSource
    profileType: PaceProfileType
    approvalStatus: ProfileApprovalStatus
    coachLocked: bool = False
    poolLengthM: int
    startMode: StartMode
    stroke: Stroke
    workoutGoal: WorkoutGoal
    targetTotalTimeSec: PosFloat
    reportingSplitGranularityM: int = 25
    legs: Annotated[list[PaceProfileLeg], Field(min_length=1)]
    modelMetadata: ModelProfileMetadata | None = None
    coachMetadata: CoachProfileMetadata | None = None
    physiologyTarget: PhysiologyTarget | None = None
    createdAtMs: NonNegInt | None = None
    approvedAtMs: NonNegInt | None = None
    approvedBy: str | None = None

    @property
    def totalDistanceM(self) -> float:
        return self.legs[-1].toM

    @property
    def is_live_eligible(self) -> bool:
        return self.approvalStatus in LIVE_ELIGIBLE_APPROVAL_STATUSES

    @model_validator(mode="after")
    def _check_consistency(self) -> ApprovedPaceProfile:
        if self.poolLengthM not in (25, 50):
            raise ValueError(f"poolLengthM must be 25 or 50, got {self.poolLengthM}")
        legs = self.legs
        # first leg begins at 0
        if abs(legs[0].fromM) > FLOAT_TOLERANCE:
            raise ValueError("first leg must start at 0 m")
        # legIndex is contiguous from 0
        for i, leg in enumerate(legs):
            if leg.legIndex != i:
                raise ValueError(f"legIndex {leg.legIndex} out of order (expected {i})")
            if leg.toM <= leg.fromM + FLOAT_TOLERANCE:
                raise ValueError(f"leg {i}: toM must be > fromM")
        # no gaps / overlaps
        for i in range(len(legs) - 1):
            if abs(legs[i + 1].fromM - legs[i].toM) > FLOAT_TOLERANCE:
                raise ValueError(
                    f"leg {i + 1} fromM {legs[i + 1].fromM} does not continue "
                    f"leg {i} toM {legs[i].toM} (gap/overlap)"
                )
        # durations sum to the target total (no silent normalization)
        total = sum(leg.targetDurationSec for leg in legs)
        if abs(total - self.targetTotalTimeSec) > FLOAT_TOLERANCE:
            raise ValueError(
                f"leg durations sum to {total}, not targetTotalTimeSec {self.targetTotalTimeSec}"
            )
        # a coach-locked profile is implicitly live-eligible only via approval status;
        # coachLocked without an eligible status is a contradiction.
        if self.coachLocked and not self.is_live_eligible:
            raise ValueError("coachLocked profile must have a live-eligible approval status")
        return self
