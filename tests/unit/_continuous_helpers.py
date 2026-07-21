"""Shared builders for continuous pace-curve tests."""

from __future__ import annotations

from contracts.continuous_pace import (
    ApprovedContinuousPaceProfile,
    ContinuousPaceCurve,
    ContinuousPacePhase,
    CurveProvenance,
    PaceCurveKnot,
    SplitTimeConstraint,
    TargetTimeConstraint,
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


def knots(*pairs: tuple[float, float]) -> tuple[PaceCurveKnot, ...]:
    return tuple(
        PaceCurveKnot(knotIndex=i, distanceM=d, targetSpeedMps=s) for i, (d, s) in enumerate(pairs)
    )


def pchip_profile(
    *,
    total: float = 100.0,
    target_time: float = 80.0,
    pool: int = 25,
    curve_knots: tuple[PaceCurveKnot, ...] | None = None,
    locked_splits: tuple[SplitTimeConstraint, ...] = (),
    phases: tuple[ContinuousPacePhase, ...] | None = None,
    source: PaceProfileSource = PaceProfileSource.COACH_AUTHORED,
    approval: ProfileApprovalStatus = ProfileApprovalStatus.COACH_APPROVED,
    start_mode: StartMode = StartMode.DIVE_START,
    stroke: Stroke = Stroke.freestyle,
    coach_locked: bool = False,
    profile_id: str = "p",
    profile_version: str = "1",
) -> ApprovedContinuousPaceProfile:
    if curve_knots is None:
        curve_knots = knots((0.0, 1.25), (total, 1.25))
    if phases is None:
        phases = (
            ContinuousPacePhase(
                phaseIndex=0, fromM=0.0, toM=total, phaseType=ContinuousPacePhaseType.SURFACE_SWIM
            ),
        )
    return ApprovedContinuousPaceProfile(
        profileId=profile_id,
        profileVersion=profile_version,
        source=source,
        profileType=PaceProfileType.EVEN_PACE,
        approvalStatus=approval,
        coachLocked=coach_locked,
        poolLengthM=pool,
        startMode=start_mode,
        stroke=stroke,
        workoutGoal=WorkoutGoal.RACE_PACE,
        totalDistanceM=total,
        targetTimeConstraint=TargetTimeConstraint(
            targetTotalTimeSec=target_time, source=TargetTimeSource.COACH
        ),
        splitTimeConstraints=locked_splits,
        curve=ContinuousPaceCurve(representation=PaceCurveRepresentation.PCHIP, knots=curve_knots),
        phases=phases,
        curveProvenance=CurveProvenance(
            generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
            targetTimeSource=TargetTimeSource.COACH,
        ),
    )
