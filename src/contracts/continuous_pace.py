"""Continuous pace-curve contracts — ApprovedPaceProfile 1.1 (ADR-038).

A profile leg / official split duration is a *time constraint* on a distance span; the
within-length pace is NOT required to be constant. The continuous target speed is carried as
an approved curve (PCHIP for native profiles, CONSTANT_SPEED only for legacy migration and
explicit templates), integrated exactly to the target total time and to any locked split
times before it may run live.

This module ADDS the 1.1 contract; it never changes the 1.0 ``ApprovedPaceProfile`` (ADR-034
authority, approval, source-priority and coach-lock decisions remain in force). Curve knots
carry a *speed* (m/s, strictly positive and finite); phases and locked splits are analytical
spans and never official wall splits (ADR-036).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from contracts._base import (
    FLOAT_TOLERANCE,
    NonEmptyStr,
    NonNegFloat,
    NonNegInt,
    PosFloat,
    StrictModel,
)
from contracts.enums import (
    ContinuousCurveGenerationMode,
    ContinuousPacePhaseType,
    PaceCurveRepresentation,
    PaceProfileSource,
    PaceProfileType,
    ProfileApprovalStatus,
    StartMode,
    Stroke,
    TargetTimeSource,
    WorkoutGoal,
)
from contracts.pace_profiles import (
    LIVE_ELIGIBLE_APPROVAL_STATUSES,
    ApprovedPaceProfile,
    CoachProfileMetadata,
    ModelProfileMetadata,
)
from contracts.physiology import PhysiologyTarget


# --------------------------------------------------------------------------- curve knots / segments
class PaceCurveKnot(StrictModel):
    """One PCHIP control knot: a target *speed* (m/s) at a distance (m)."""

    knotIndex: NonNegInt
    distanceM: Annotated[float, Field(ge=0)]
    targetSpeedMps: PosFloat


class ConstantSpeedCurveSegment(StrictModel):
    """One constant-speed span (legacy migration / explicit template only)."""

    segmentIndex: NonNegInt
    fromM: Annotated[float, Field(ge=0)]
    toM: PosFloat
    targetSpeedMps: PosFloat


class ContinuousPaceCurve(StrictModel):
    """The approved within-length target-speed curve.

    Exactly one representation is populated: PCHIP → ``knots`` (>= 2, first at 0 m, last at
    total distance, strictly increasing, positive finite speeds); CONSTANT_SPEED →
    ``segments`` (contiguous, gap/overlap-free, preserving legacy leg boundaries).
    """

    representation: PaceCurveRepresentation
    knots: tuple[PaceCurveKnot, ...] = ()
    segments: tuple[ConstantSpeedCurveSegment, ...] = ()

    @model_validator(mode="after")
    def _check_curve(self) -> ContinuousPaceCurve:
        if self.representation is PaceCurveRepresentation.PCHIP:
            if self.segments:
                raise ValueError("PCHIP curve must not carry constant-speed segments")
            knots = self.knots
            if len(knots) < 2:
                raise ValueError("a PCHIP curve needs at least two knots")
            if abs(knots[0].distanceM) > FLOAT_TOLERANCE:
                raise ValueError("first knot must be at 0 m")
            for i, knot in enumerate(knots):
                if knot.knotIndex != i:
                    raise ValueError(f"knotIndex {knot.knotIndex} out of order (expected {i})")
            for i in range(len(knots) - 1):
                if knots[i + 1].distanceM <= knots[i].distanceM + FLOAT_TOLERANCE:
                    raise ValueError(
                        f"knot distances must be strictly increasing: "
                        f"{knots[i].distanceM} then {knots[i + 1].distanceM}"
                    )
        elif self.representation is PaceCurveRepresentation.CONSTANT_SPEED:
            if self.knots:
                raise ValueError("CONSTANT_SPEED curve must not carry PCHIP knots")
            segs = self.segments
            if len(segs) < 1:
                raise ValueError("a CONSTANT_SPEED curve needs at least one segment")
            if abs(segs[0].fromM) > FLOAT_TOLERANCE:
                raise ValueError("first segment must start at 0 m")
            for i, seg in enumerate(segs):
                if seg.segmentIndex != i:
                    raise ValueError(f"segmentIndex {seg.segmentIndex} out of order (expected {i})")
                if seg.toM <= seg.fromM + FLOAT_TOLERANCE:
                    raise ValueError(f"segment {i}: toM must be > fromM")
            for i in range(len(segs) - 1):
                if abs(segs[i + 1].fromM - segs[i].toM) > FLOAT_TOLERANCE:
                    raise ValueError(f"segment {i + 1} gap/overlap with segment {i}")
        return self

    @property
    def totalDistanceM(self) -> float:
        if self.representation is PaceCurveRepresentation.PCHIP:
            return self.knots[-1].distanceM
        return self.segments[-1].toM


# --------------------------------------------------------------------------- phases / constraints
class ContinuousPacePhase(StrictModel):
    """An analytical within-length phase span. Not an official wall/split boundary."""

    phaseIndex: NonNegInt
    fromM: Annotated[float, Field(ge=0)]
    toM: PosFloat
    phaseType: ContinuousPacePhaseType


class TargetTimeConstraint(StrictModel):
    targetTotalTimeSec: PosFloat
    source: TargetTimeSource
    toleranceSec: NonNegFloat = 1e-6
    coachLocked: bool = False


class SplitTimeConstraint(StrictModel):
    """A locked/soft time constraint on a distance span. Boundaries follow pool geometry."""

    splitIndex: NonNegInt
    fromM: Annotated[float, Field(ge=0)]
    toM: PosFloat
    targetDurationSec: PosFloat
    lockedByCoach: bool = False

    @model_validator(mode="after")
    def _check_span(self) -> SplitTimeConstraint:
        if self.toM <= self.fromM + FLOAT_TOLERANCE:
            raise ValueError(f"split {self.splitIndex}: toM must be > fromM")
        return self


# --------------------------------------------------------------------------- provenance / validation
class CurveProvenance(StrictModel):
    generationMode: ContinuousCurveGenerationMode
    targetTimeSource: TargetTimeSource
    modelVersion: str | None = None
    generalModelVersion: str | None = None
    personalCalibrationVersion: str | None = None
    coachConstraintVersion: str | None = None
    profileGenerationId: str | None = None
    curveExtractionVersion: str | None = None
    smoothingMethod: str | None = None
    sourceDataQuality: str | None = None
    migratedFromSchemaVersion: str | None = None
    migrationVersion: str | None = None
    legacyProfileId: str | None = None
    legacyProfileVersion: str | None = None


class CurveValidationSummary(StrictModel):
    """Compiler-authoritative summary. The compiler recomputes rather than trusting input."""

    integratedTotalTimeSec: NonNegFloat
    targetTotalTimeSec: NonNegFloat
    totalReconciliationErrorSec: NonNegFloat
    maxSplitReconciliationErrorSec: NonNegFloat
    minTargetSpeedMps: PosFloat
    maxTargetSpeedMps: PosFloat
    phaseCount: NonNegInt
    knotCount: NonNegInt
    compiledIntervalCount: NonNegInt
    representation: PaceCurveRepresentation
    compilerVersion: NonEmptyStr
    lookupResolutionM: PosFloat
    physicalBoundsChecked: bool
    validationPassed: bool


# --------------------------------------------------------------------------- the 1.1 profile
class ApprovedContinuousPaceProfile(StrictModel):
    """Approved continuous pace profile (schema 1.1).

    Backward compatibility: this is an ADDITIVE contract. Split/leg durations are time
    constraints; the within-length pace comes from the approved ``curve``. Only a profile
    with ``curveValidationSummary.validationPassed`` may run live (enforced by the compiler).
    """

    schemaVersion: Literal["1.1"] = "1.1"
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
    totalDistanceM: PosFloat
    targetTimeConstraint: TargetTimeConstraint
    splitTimeConstraints: tuple[SplitTimeConstraint, ...] = ()
    curve: ContinuousPaceCurve
    phases: Annotated[tuple[ContinuousPacePhase, ...], Field(min_length=1)]
    curveProvenance: CurveProvenance
    curveValidationSummary: CurveValidationSummary | None = None
    reportingSplitGranularityM: int = 25
    modelMetadata: ModelProfileMetadata | None = None
    coachMetadata: CoachProfileMetadata | None = None
    physiologyTarget: PhysiologyTarget | None = None
    createdAtMs: NonNegInt | None = None
    approvedAtMs: NonNegInt | None = None
    approvedBy: str | None = None

    @property
    def is_live_eligible(self) -> bool:
        return self.approvalStatus in LIVE_ELIGIBLE_APPROVAL_STATUSES

    @model_validator(mode="after")
    def _check_consistency(self) -> ApprovedContinuousPaceProfile:
        if self.poolLengthM not in (25, 50):
            raise ValueError(f"poolLengthM must be 25 or 50, got {self.poolLengthM}")
        total = self.totalDistanceM

        # curve must cover exactly the total distance
        if abs(self.curve.totalDistanceM - total) > FLOAT_TOLERANCE:
            raise ValueError(
                f"curve covers {self.curve.totalDistanceM} m, profile total is {total} m"
            )
        # last PCHIP knot / last constant segment ends at total distance
        # (curve validator already checked strictly-increasing / contiguity)

        # phases: contiguous coverage 0 -> total, no gap/overlap
        phases = self.phases
        if abs(phases[0].fromM) > FLOAT_TOLERANCE:
            raise ValueError("first phase must start at 0 m")
        for i, phase in enumerate(phases):
            if phase.phaseIndex != i:
                raise ValueError(f"phaseIndex {phase.phaseIndex} out of order (expected {i})")
            if phase.toM <= phase.fromM + FLOAT_TOLERANCE:
                raise ValueError(f"phase {i}: toM must be > fromM")
        for i in range(len(phases) - 1):
            if abs(phases[i + 1].fromM - phases[i].toM) > FLOAT_TOLERANCE:
                raise ValueError(f"phase {i + 1} gap/overlap with phase {i}")
        if abs(phases[-1].toM - total) > FLOAT_TOLERANCE:
            raise ValueError(f"last phase must end at total distance {total}")

        # split constraints: within [0, total], boundaries pool-aligned, no overlap, locked
        # sum consistent with target when they cover the whole distance
        pool = self.poolLengthM
        splits = sorted(self.splitTimeConstraints, key=lambda s: s.fromM)
        prev_to = 0.0
        covered = 0.0
        locked_sum = 0.0
        target = self.targetTimeConstraint.targetTotalTimeSec
        for split in splits:
            if split.toM > total + FLOAT_TOLERANCE:
                raise ValueError(f"split {split.splitIndex} exceeds total distance {total}")
            for boundary in (split.fromM, split.toM):
                ratio = boundary / pool
                if abs(ratio - round(ratio)) > 1e-6:
                    raise ValueError(
                        f"split {split.splitIndex} boundary {boundary} is not a "
                        f"{pool} m wall multiple"
                    )
            if split.fromM < prev_to - FLOAT_TOLERANCE:
                raise ValueError(f"split {split.splitIndex} overlaps a previous split")
            prev_to = split.toM
            covered += split.toM - split.fromM
            if split.lockedByCoach:
                locked_sum += split.targetDurationSec
        # if locked splits cover the entire distance, their sum must equal the target
        if splits and abs(covered - total) <= FLOAT_TOLERANCE:
            all_locked = all(s.lockedByCoach for s in splits)
            if all_locked and abs(locked_sum - target) > max(
                self.targetTimeConstraint.toleranceSec, FLOAT_TOLERANCE
            ):
                raise ValueError(f"locked split durations sum to {locked_sum}, not target {target}")
        # partial locked coverage: remaining time must stay positive
        if locked_sum > target + FLOAT_TOLERANCE:
            raise ValueError(f"locked split durations {locked_sum} exceed target total {target}")

        if self.coachLocked and not self.is_live_eligible:
            raise ValueError("coachLocked profile must have a live-eligible approval status")
        return self


#: A profile of either schema version. Selection/registry/compiler accept both.
ApprovedPaceProfileVersion = ApprovedPaceProfile | ApprovedContinuousPaceProfile
