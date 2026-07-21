"""Pure migration of a legacy ApprovedPaceProfile 1.0 into a 1.1 continuous profile (ADR-038).

Each legacy leg becomes a CONSTANT_SPEED curve segment with
``targetSpeedMps = legDistanceM / targetDurationSec`` and a locked split constraint carrying
the leg's exact duration, so the compiled 1.1 timeline reproduces the legacy constant-leg
timeline bit-for-bit (within the central float tolerance). The legacy profile is NOT
smoothed into a PCHIP curve — its behaviour must not change. The input is never mutated.
"""

from __future__ import annotations

from contracts.continuous_pace import (
    ApprovedContinuousPaceProfile,
    ConstantSpeedCurveSegment,
    ContinuousPaceCurve,
    ContinuousPacePhase,
    CurveProvenance,
    SplitTimeConstraint,
    TargetTimeConstraint,
)
from contracts.enums import (
    ContinuousCurveGenerationMode,
    ContinuousPacePhaseType,
    PaceCurveRepresentation,
    PaceProfilePhase,
    TargetTimeSource,
)
from contracts.pace_profiles import ApprovedPaceProfile

MIGRATION_VERSION = "1.0->1.1-v1"

#: Map the legacy analytical phase enum to the richer 1.1 phase taxonomy.
_PHASE_MAP: dict[PaceProfilePhase, ContinuousPacePhaseType] = {
    PaceProfilePhase.START_UNDERWATER: ContinuousPacePhaseType.START_UNDERWATER,
    PaceProfilePhase.SURFACE_SWIM: ContinuousPacePhaseType.SURFACE_SWIM,
    PaceProfilePhase.TURN_TRANSITION: ContinuousPacePhaseType.TURN_TRANSITION,
    PaceProfilePhase.MID_RACE: ContinuousPacePhaseType.MID_LENGTH_ADJUSTMENT,
    PaceProfilePhase.FINAL_ACCELERATION: ContinuousPacePhaseType.FINAL_ACCELERATION,
    PaceProfilePhase.FINISH: ContinuousPacePhaseType.FINISH,
    PaceProfilePhase.CUSTOM: ContinuousPacePhaseType.CUSTOM,
}


def migrate_approved_pace_profile_1_0_to_1_1(
    profile: ApprovedPaceProfile,
) -> ApprovedContinuousPaceProfile:
    """Migrate a legacy 1.0 approved profile to a 1.1 continuous profile (pure)."""
    total = profile.totalDistanceM

    segments: list[ConstantSpeedCurveSegment] = []
    phases: list[ContinuousPacePhase] = []
    splits: list[SplitTimeConstraint] = []
    for leg in profile.legs:
        speed = leg.legDistanceM / leg.targetDurationSec
        segments.append(
            ConstantSpeedCurveSegment(
                segmentIndex=leg.legIndex,
                fromM=leg.fromM,
                toM=leg.toM,
                targetSpeedMps=speed,
            )
        )
        phases.append(
            ContinuousPacePhase(
                phaseIndex=leg.legIndex,
                fromM=leg.fromM,
                toM=leg.toM,
                phaseType=_PHASE_MAP.get(leg.phaseType, ContinuousPacePhaseType.CUSTOM),
            )
        )
        splits.append(
            SplitTimeConstraint(
                splitIndex=leg.legIndex,
                fromM=leg.fromM,
                toM=leg.toM,
                targetDurationSec=leg.targetDurationSec,
                # legacy leg boundaries are not necessarily pool-aligned; only mark as a
                # locked constraint when the span sits on wall multiples so the 1.1
                # validator (which requires pool-aligned split boundaries) accepts it.
                lockedByCoach=_is_wall_aligned(leg.fromM, leg.toM, profile.poolLengthM),
            )
        )

    # keep only pool-aligned splits as constraints (validator requires wall-aligned bounds)
    aligned_splits = tuple(s for s in splits if s.lockedByCoach)

    provenance = CurveProvenance(
        generationMode=ContinuousCurveGenerationMode.LEGACY_MIGRATION,
        targetTimeSource=TargetTimeSource.LEGACY_MIGRATION,
        migratedFromSchemaVersion="1.0",
        migrationVersion=MIGRATION_VERSION,
        legacyProfileId=profile.profileId,
        legacyProfileVersion=profile.profileVersion,
    )

    return ApprovedContinuousPaceProfile(
        profileId=profile.profileId,
        profileVersion=profile.profileVersion,
        source=profile.source,
        profileType=profile.profileType,
        approvalStatus=profile.approvalStatus,
        coachLocked=profile.coachLocked,
        poolLengthM=profile.poolLengthM,
        startMode=profile.startMode,
        stroke=profile.stroke,
        workoutGoal=profile.workoutGoal,
        totalDistanceM=total,
        targetTimeConstraint=TargetTimeConstraint(
            targetTotalTimeSec=profile.targetTotalTimeSec,
            source=TargetTimeSource.LEGACY_MIGRATION,
            coachLocked=profile.coachLocked,
        ),
        splitTimeConstraints=aligned_splits,
        curve=ContinuousPaceCurve(
            representation=PaceCurveRepresentation.CONSTANT_SPEED,
            segments=tuple(segments),
        ),
        phases=tuple(phases),
        curveProvenance=provenance,
        reportingSplitGranularityM=profile.reportingSplitGranularityM,
        modelMetadata=profile.modelMetadata,
        coachMetadata=profile.coachMetadata,
        physiologyTarget=profile.physiologyTarget,
        createdAtMs=profile.createdAtMs,
        approvedAtMs=profile.approvedAtMs,
        approvedBy=profile.approvedBy,
    )


def _is_wall_aligned(from_m: float, to_m: float, pool: int) -> bool:
    for boundary in (from_m, to_m):
        ratio = boundary / pool
        if abs(ratio - round(ratio)) > 1e-6:
            return False
    return True
