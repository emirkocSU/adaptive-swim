"""Deterministic scenario library for the headless simulator (Commit 8).

Each builder returns a fully specified :class:`SimulationScenario`. Every scenario is pure
and deterministic (fixed seeds, no randomness beyond the seeded swimmer). Together they
cover: even/negative-split/positive-fade PCHIP curves, coach-locked splits, a StopPause with
external tracked alignment, a coach continuous-curve reset at a wall, a migrated legacy 1.0
profile, and an explicit constant-speed curve. Wall touches are built from the REAL compiled
ghost timeline so the ghost the swimmer follows is the production plan.
"""

from __future__ import annotations

from contracts.continuous_pace import (
    ApprovedContinuousPaceProfile,
    ConstantSpeedCurveSegment,
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
    PaceProfilePhase,
    PaceProfileSource,
    PaceProfileType,
    ProfileApprovalStatus,
    StartMode,
    Stroke,
    TargetTimeSource,
    WorkoutGoal,
)
from contracts.pace_profiles import ApprovedPaceProfile, PaceProfileLeg
from contracts.workout import WorkoutTemplateV1_1
from simulator.harness import (
    ScenarioStop,
    SimulationScenario,
    ghost_wall_targets,
    resolve_start_mode_for,
)
from simulator.virtual_swimmer import SwimmerBehaviour, swim_walls

_POOL = 25


def _workout(distance: int, pace: float = 70.0) -> WorkoutTemplateV1_1:
    return WorkoutTemplateV1_1.model_validate(
        {
            "schemaVersion": "1.1",
            "name": "sim-wk",
            "poolLengthM": _POOL,
            "stroke": "freestyle",
            "startPolicy": {
                "defaultMode": "DIVE_START",
                "allowBlockOverride": True,
                "allowRepeatOverride": True,
            },
            "workoutGoal": "RACE_PACE",
            "blocks": [
                {
                    "type": "repeat",
                    "label": "main",
                    "repetitions": 1,
                    "distanceM": distance,
                    "rest": {"type": "none"},
                    "segments": [
                        {
                            "fromM": 0,
                            "toM": distance,
                            "mode": "even_pace",
                            "targetPaceSecPer100M": pace,
                        }
                    ],
                }
            ],
            "repeatOverrides": [],
        }
    )


def _pchip_profile(
    profile_id: str,
    total_distance: float,
    target_time: float,
    knots: list[tuple[float, float]],
    *,
    profile_type: PaceProfileType = PaceProfileType.EVEN_PACE,
    splits: tuple[SplitTimeConstraint, ...] = (),
    source: PaceProfileSource = PaceProfileSource.COACH_AUTHORED,
) -> ApprovedContinuousPaceProfile:
    return ApprovedContinuousPaceProfile(
        profileId=profile_id,
        profileVersion="1",
        source=source,
        profileType=profile_type,
        approvalStatus=ProfileApprovalStatus.COACH_APPROVED,
        poolLengthM=_POOL,
        startMode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        workoutGoal=WorkoutGoal.RACE_PACE,
        totalDistanceM=total_distance,
        targetTimeConstraint=TargetTimeConstraint(
            targetTotalTimeSec=target_time, source=TargetTimeSource.COACH
        ),
        splitTimeConstraints=splits,
        curve=ContinuousPaceCurve(
            representation=PaceCurveRepresentation.PCHIP,
            knots=tuple(
                PaceCurveKnot(knotIndex=i, distanceM=d, targetSpeedMps=s)
                for i, (d, s) in enumerate(knots)
            ),
        ),
        phases=(
            ContinuousPacePhase(
                phaseIndex=0,
                fromM=0.0,
                toM=total_distance,
                phaseType=ContinuousPacePhaseType.SURFACE_SWIM,
            ),
        ),
        curveProvenance=CurveProvenance(
            generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
            targetTimeSource=TargetTimeSource.COACH,
        ),
    )


def _touches(
    profile: ApprovedContinuousPaceProfile | ApprovedPaceProfile,
    workout: WorkoutTemplateV1_1,
    total_distance: float,
    behaviour: SwimmerBehaviour,
    seed: int,
) -> tuple[tuple[int, float, int], ...]:
    resolved = resolve_start_mode_for(workout)
    targets = ghost_wall_targets(
        profile,
        pool_length_m=_POOL,
        resolved_start_mode=resolved,
        stroke=Stroke.freestyle,
        total_distance_m=total_distance,
    )
    walls = swim_walls(
        pool_length_m=_POOL,
        total_distance_m=total_distance,
        target_time_at_wall_ms=targets,
        behaviour=behaviour,
        seed=seed,
    )
    return tuple((w.lengthIndex, w.distanceM, w.wallTimestampMs) for w in walls)


# --------------------------------------------------------------------------- scenarios
def scenario_even_on_plan() -> SimulationScenario:
    wk = _workout(100)
    prof = _pchip_profile("even100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    behaviour = SwimmerBehaviour(paceBiasFactor=1.0)
    return SimulationScenario(
        name="even-on-plan",
        seed=1001,
        workout=wk,
        profile=prof,
        wallTouches=_touches(prof, wk, 100.0, behaviour, 1001),
        description="100 m even PCHIP curve, swimmer exactly on plan.",
    )


def scenario_negative_split() -> SimulationScenario:
    wk = _workout(200)
    prof = _pchip_profile(
        "neg200",
        200.0,
        170.0,
        [(0.0, 1.12), (100.0, 1.15), (200.0, 1.24)],
        profile_type=PaceProfileType.NEGATIVE_SPLIT,
    )
    behaviour = SwimmerBehaviour(paceBiasFactor=1.0, jitterFractionPerLength=0.01)
    return SimulationScenario(
        name="negative-split",
        seed=1002,
        workout=wk,
        profile=prof,
        wallTouches=_touches(prof, wk, 200.0, behaviour, 1002),
        description="200 m negative-split PCHIP, small deterministic jitter.",
    )


def scenario_positive_fade() -> SimulationScenario:
    wk = _workout(100)
    prof = _pchip_profile(
        "sprint100",
        100.0,
        60.0,
        [(0.0, 1.85), (50.0, 1.7), (100.0, 1.55)],
        profile_type=PaceProfileType.SPRINT_POSITIVE_SPLIT,
    )
    # a natural sprint fade — swimmer slows compounding each length (not an incident)
    behaviour = SwimmerBehaviour(paceBiasFactor=1.0, fadeFactorPerLength=1.03)
    return SimulationScenario(
        name="positive-fade",
        seed=1003,
        workout=wk,
        profile=prof,
        wallTouches=_touches(prof, wk, 100.0, behaviour, 1003),
        description="100 m sprint with a natural positive split / fade (not an incident).",
    )


def scenario_locked_splits() -> SimulationScenario:
    wk = _workout(100)
    prof = _pchip_profile(
        "locked100",
        100.0,
        80.0,
        [(0.0, 1.30), (50.0, 1.15), (100.0, 1.32)],
        splits=(
            SplitTimeConstraint(
                splitIndex=0, fromM=0.0, toM=50.0, targetDurationSec=42.0, lockedByCoach=True
            ),
        ),
    )
    behaviour = SwimmerBehaviour(paceBiasFactor=1.0)
    return SimulationScenario(
        name="locked-splits",
        seed=1004,
        workout=wk,
        profile=prof,
        wallTouches=_touches(prof, wk, 100.0, behaviour, 1004),
        description="100 m curve with a coach-locked first 50 m split (42 s of 80 s).",
    )


def scenario_stop_pause() -> SimulationScenario:
    wk = _workout(100)
    prof = _pchip_profile("stop100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    behaviour = SwimmerBehaviour(paceBiasFactor=1.0)
    touches = _touches(prof, wk, 100.0, behaviour, 1005)
    return SimulationScenario(
        name="stop-pause",
        seed=1005,
        workout=wk,
        profile=prof,
        wallTouches=touches,
        stop=ScenarioStop(afterLengthIndex=1, durationMs=15_000, trackedAlignmentDistanceM=60.0),
        description="100 m with an externally tracked StopPause resolved at the next wall.",
    )


def scenario_coach_continuous_reset() -> SimulationScenario:
    wk = _workout(100)
    prof = _pchip_profile("base100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    replacement = _pchip_profile("repl100", 100.0, 100.0, [(0.0, 1.0), (100.0, 1.0)])
    behaviour = SwimmerBehaviour(paceBiasFactor=1.0)
    return SimulationScenario(
        name="coach-continuous-reset",
        seed=1006,
        workout=wk,
        profile=prof,
        wallTouches=_touches(prof, wk, 100.0, behaviour, 1006),
        replacementProfile=replacement,
        replacementAfterLengthIndex=1,
        description="Coach swaps in a slower continuous curve at the 50 m wall.",
    )


def scenario_migrated_legacy() -> SimulationScenario:
    from swimcore.pacing.continuous_migration import (
        migrate_approved_pace_profile_1_0_to_1_1,
    )

    legacy = ApprovedPaceProfile(
        profileId="legacy100",
        profileVersion="1",
        source=PaceProfileSource.COACH_AUTHORED,
        profileType=PaceProfileType.NEGATIVE_SPLIT,
        approvalStatus=ProfileApprovalStatus.COACH_APPROVED,
        poolLengthM=_POOL,
        startMode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        workoutGoal=WorkoutGoal.RACE_PACE,
        targetTotalTimeSec=82.0,
        legs=[
            PaceProfileLeg(
                legIndex=0,
                fromM=0.0,
                toM=50.0,
                targetDurationSec=42.0,
                phaseType=PaceProfilePhase.SURFACE_SWIM,
            ),
            PaceProfileLeg(
                legIndex=1,
                fromM=50.0,
                toM=100.0,
                targetDurationSec=40.0,
                phaseType=PaceProfilePhase.FINISH,
            ),
        ],
    )
    migrated = migrate_approved_pace_profile_1_0_to_1_1(legacy)
    wk = _workout(100)
    behaviour = SwimmerBehaviour(paceBiasFactor=1.0)
    return SimulationScenario(
        name="migrated-legacy",
        seed=1007,
        workout=wk,
        profile=migrated,
        wallTouches=_touches(migrated, wk, 100.0, behaviour, 1007),
        description="Legacy 1.0 profile migrated to a 1.1 constant-speed curve.",
    )


def scenario_constant_speed_template() -> SimulationScenario:
    wk = _workout(100)
    prof = ApprovedContinuousPaceProfile(
        profileId="const100",
        profileVersion="1",
        source=PaceProfileSource.TEMPLATE,
        profileType=PaceProfileType.EVEN_PACE,
        approvalStatus=ProfileApprovalStatus.COACH_APPROVED,
        poolLengthM=_POOL,
        startMode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        workoutGoal=WorkoutGoal.RACE_PACE,
        totalDistanceM=100.0,
        targetTimeConstraint=TargetTimeConstraint(
            targetTotalTimeSec=80.0, source=TargetTimeSource.TEMPLATE
        ),
        curve=ContinuousPaceCurve(
            representation=PaceCurveRepresentation.CONSTANT_SPEED,
            segments=(
                ConstantSpeedCurveSegment(segmentIndex=0, fromM=0.0, toM=50.0, targetSpeedMps=1.25),
                ConstantSpeedCurveSegment(
                    segmentIndex=1, fromM=50.0, toM=100.0, targetSpeedMps=1.25
                ),
            ),
        ),
        phases=(
            ContinuousPacePhase(
                phaseIndex=0,
                fromM=0.0,
                toM=100.0,
                phaseType=ContinuousPacePhaseType.SURFACE_SWIM,
            ),
        ),
        curveProvenance=CurveProvenance(
            generationMode=ContinuousCurveGenerationMode.TEMPLATE,
            targetTimeSource=TargetTimeSource.TEMPLATE,
        ),
    )
    behaviour = SwimmerBehaviour(paceBiasFactor=1.0)
    return SimulationScenario(
        name="constant-speed-template",
        seed=1008,
        workout=wk,
        profile=prof,
        wallTouches=_touches(prof, wk, 100.0, behaviour, 1008),
        description="Explicit CONSTANT_SPEED template curve (non-migration path).",
    )


#: Ordered scenario builders. Deterministic; the order is stable for golden generation.
ALL_SCENARIOS = (
    scenario_even_on_plan,
    scenario_negative_split,
    scenario_positive_fade,
    scenario_locked_splits,
    scenario_stop_pause,
    scenario_coach_continuous_reset,
    scenario_migrated_legacy,
    scenario_constant_speed_template,
)

SCENARIO_BY_NAME = {builder().name: builder for builder in ALL_SCENARIOS}


def build_all_scenarios() -> list[SimulationScenario]:
    return [builder() for builder in ALL_SCENARIOS]
