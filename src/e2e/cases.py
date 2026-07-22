"""The Phase 1 vertical-slice case matrix (ADR-041).

Ten required closure cases plus the three remaining required failure scenarios, so that
``--all`` covers both the Phase 1 closure matrix and the full eight-scenario Commit 8
regression set end to end.

Case definitions are data. Every workout, profile and scenario here is built from the real
contracts; no domain behaviour is re-implemented.
"""

from __future__ import annotations

from collections.abc import Callable

from contracts.continuous_pace import (
    ApprovedContinuousPaceProfile,
    ContinuousPaceCurve,
    ContinuousPacePhase,
    CurveProvenance,
    PaceCurveKnot,
    TargetTimeConstraint,
)
from contracts.enums import (
    ContinuousCurveGenerationMode,
    ContinuousPacePhaseType,
    CurveEvidenceLevel,
    CurveOrigin,
    PaceCurveRepresentation,
    PaceProfilePhase,
    PaceProfileSource,
    PaceProfileType,
    ProfileApprovalStatus,
    StartMode,
    Stroke,
    TargetTimeSource,
    VisualShapeSource,
    WorkoutGoal,
)
from contracts.pace_profiles import ApprovedPaceProfile, PaceProfileLeg
from contracts.workout import WorkoutTemplateV1_0, WorkoutTemplateV1_1
from e2e.types import Phase1E2ECase, Phase1ExpectedOutcome
from simulator.harness import SimulationScenario, SwimmerParams
from simulator.scenarios import SCENARIO_BY_NAME, SCENARIO_SET_VERSION
from swimcore.pacing.continuous_migration import migrate_approved_pace_profile_1_0_to_1_1
from swimcore.workout.migrations import migrate_workout_1_0_to_1_1

CASE_VERSION = "1.0.0"


# --------------------------------------------------------------------------- fixtures
def _workout(
    *, distance: int, pool: int = 25, pace: float = 70.0, name: str = "e2e-wk"
) -> WorkoutTemplateV1_1:
    return WorkoutTemplateV1_1.model_validate(
        {
            "schemaVersion": "1.1",
            "name": name,
            "poolLengthM": pool,
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


def _workout_v1_0(
    *, distance: int, pool: int = 25, pace: float = 70.0, name: str = "e2e-wk-v1"
) -> WorkoutTemplateV1_0:
    return WorkoutTemplateV1_0.model_validate(
        {
            "schemaVersion": "1.0",
            "name": name,
            "poolLengthM": pool,
            "stroke": "freestyle",
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
        }
    )


def _continuous_profile(
    *,
    profile_id: str,
    pool: int,
    total_distance: float,
    target_time: float,
    knots: list[tuple[float, float]],
    provenance: CurveProvenance | None = None,
) -> ApprovedContinuousPaceProfile:
    return ApprovedContinuousPaceProfile(
        profileId=profile_id,
        profileVersion="1",
        source=PaceProfileSource.COACH_AUTHORED,
        profileType=PaceProfileType.EVEN_PACE,
        approvalStatus=ProfileApprovalStatus.COACH_APPROVED,
        coachLocked=False,
        poolLengthM=pool,
        startMode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        workoutGoal=WorkoutGoal.RACE_PACE,
        totalDistanceM=total_distance,
        targetTimeConstraint=TargetTimeConstraint(
            targetTotalTimeSec=target_time, source=TargetTimeSource.COACH
        ),
        curve=ContinuousPaceCurve(
            representation=PaceCurveRepresentation.PCHIP,
            knots=tuple(
                PaceCurveKnot(knotIndex=index, distanceM=distance, targetSpeedMps=speed)
                for index, (distance, speed) in enumerate(knots)
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
        curveProvenance=(
            provenance
            if provenance is not None
            else CurveProvenance(
                generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
                targetTimeSource=TargetTimeSource.COACH,
            )
        ),
    )


def _legacy_profile(profile_id: str = "e2e-legacy100") -> ApprovedPaceProfile:
    return ApprovedPaceProfile(
        profileId=profile_id,
        profileVersion="1",
        source=PaceProfileSource.COACH_AUTHORED,
        profileType=PaceProfileType.NEGATIVE_SPLIT,
        approvalStatus=ProfileApprovalStatus.COACH_APPROVED,
        poolLengthM=25,
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


#: Dataset-evidence provenance (ADR-039): a bounded operational target envelope derived from
#: a coarse race prior with a training-domain correction — never measured velocity.
_DATASET_EVIDENCE_PROVENANCE = CurveProvenance(
    generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
    targetTimeSource=TargetTimeSource.COACH,
    curveOrigin=CurveOrigin.RACE_PRIOR_TRAINING_CORRECTED,
    curveEvidenceLevel=CurveEvidenceLevel.COARSE_SPLIT_DERIVED,
    visualShapeSource=VisualShapeSource.BOUNDED_TEMPLATE,
    continuousCurveGroundTruth=False,
    trainingDomainCorrectionApplied=True,
    trainingContextCompleteness=0.4,
    baselineVersion="baseline-even-split-1.0.0",
    sourceDatasetAssetIds=(
        "adaptive_swim_unified_official_pacing_all_sources_v3",
        "adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1",
    ),
    sourceDatasetManifestVersions=("1.1.0", "1.1.0"),
)


# --------------------------------------------------------------------------- cases 1-3, 9, 10
def case_normal_continuous_completion() -> Phase1E2ECase:
    workout = _workout(distance=100, name="e2e-normal-100")
    profile = _continuous_profile(
        profile_id="e2e-normal100",
        pool=25,
        total_distance=100.0,
        target_time=80.0,
        knots=[(0.0, 1.25), (50.0, 1.25), (100.0, 1.25)],
    )
    scenario = SimulationScenario(
        scenarioId="e2e-normal-continuous-completion",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=workout,
        profile=profile,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        description="Phase 1 e2e: normal 100 m continuous completion.",
    )
    return Phase1E2ECase(
        caseId="normal-continuous-completion",
        caseVersion=CASE_VERSION,
        seed=42,
        workout=workout,
        paceProfiles=(profile,),
        selectedProfileId=profile.profileId,
        scenario=scenario,
        expectedOutcome=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stoppedDurationMs=0,
            finalProfileId=profile.profileId,
            finalProfileSource="COACH_AUTHORED",
            finalProfileCoachLocked=False,
        ),
        description=(
            "Workout 1.1, 25 m pool, continuous PCHIP profile, completed session with no "
            "StopPause and no coach reset."
        ),
    )


def case_legacy_profile_compatibility() -> Phase1E2ECase:
    source_workout = _workout_v1_0(distance=100, name="e2e-legacy-100")
    workout = migrate_workout_1_0_to_1_1(
        source_workout,
        explicit_default_start_mode=StartMode.DIVE_START,
        workout_goal=WorkoutGoal.RACE_PACE,
    )
    profile = _legacy_profile()
    scenario = SimulationScenario(
        scenarioId="e2e-legacy-profile-compatibility",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=workout,
        profile=profile,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        description="Phase 1 e2e: legacy ApprovedPaceProfile 1.0 constant-leg path.",
    )
    return Phase1E2ECase(
        caseId="legacy-profile-compatibility",
        caseVersion=CASE_VERSION,
        seed=42,
        workout=workout,
        paceProfiles=(profile,),
        selectedProfileId=profile.profileId,
        scenario=scenario,
        sourceWorkoutV1_0=source_workout,
        sourceWorkoutDefaultStartMode=StartMode.DIVE_START,
        sourceWorkoutGoal=WorkoutGoal.RACE_PACE,
        expectedOutcome=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stoppedDurationMs=0,
            finalProfileId=profile.profileId,
            finalProfileSource="COACH_AUTHORED",
            finalProfileCoachLocked=False,
        ),
        description=(
            "Workout 1.0 is parsed and explicitly migrated into the runtime Workout 1.1 "
            "contract, while ApprovedPaceProfile 1.0 runs the legacy constant-leg compiler; "
            "the complete chain still produces a journal, replay state and report."
        ),
    )


def case_migrated_profile_equivalence() -> Phase1E2ECase:
    workout = _workout(distance=100, name="e2e-migrated-100")
    legacy = _legacy_profile("e2e-migration-source")
    migrated = migrate_approved_pace_profile_1_0_to_1_1(legacy)
    scenario = SimulationScenario(
        scenarioId="e2e-migrated-profile-equivalence",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=workout,
        profile=migrated,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        description="Phase 1 e2e: migrated 1.0 -> 1.1 profile equivalence.",
    )
    return Phase1E2ECase(
        caseId="migrated-profile-equivalence",
        caseVersion=CASE_VERSION,
        seed=42,
        workout=workout,
        paceProfiles=(migrated,),
        selectedProfileId=migrated.profileId,
        scenario=scenario,
        equivalenceProfile=legacy,
        expectedOutcome=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stoppedDurationMs=0,
            finalProfileId=migrated.profileId,
        ),
        description=(
            "The same legacy profile compiled directly and after the pure 1.0 -> 1.1 "
            "migration must yield identical timelines, wall targets and report split "
            "targets."
        ),
    )


def case_dataset_evidence_provenance() -> Phase1E2ECase:
    workout = _workout(distance=100, name="e2e-evidence-100")
    profile = _continuous_profile(
        profile_id="e2e-evidence100",
        pool=25,
        total_distance=100.0,
        target_time=80.0,
        knots=[(0.0, 1.28), (50.0, 1.25), (100.0, 1.22)],
        provenance=_DATASET_EVIDENCE_PROVENANCE,
    )
    scenario = SimulationScenario(
        scenarioId="e2e-dataset-evidence-provenance",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=workout,
        profile=profile,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        description="Phase 1 e2e: coarse-split-derived operational target envelope.",
    )
    return Phase1E2ECase(
        caseId="dataset-evidence-provenance",
        caseVersion=CASE_VERSION,
        seed=42,
        workout=workout,
        paceProfiles=(profile,),
        selectedProfileId=profile.profileId,
        scenario=scenario,
        expectedOutcome=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stoppedDurationMs=0,
            datasetEvidenceAssetIds=(
                "adaptive_swim_unified_official_pacing_all_sources_v3",
                "adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1",
            ),
            curveEvidenceLevel="COARSE_SPLIT_DERIVED",
            requireNotGroundTruth=True,
        ),
        description=(
            "A coarse-split-derived, bounded-template profile runs in the deterministic "
            "runtime; the report carries its dataset asset ids as evidence metadata without "
            "presenting it as measured velocity, and no raw dataset is read."
        ),
    )


def case_fifty_metre_pool_official_distance() -> Phase1E2ECase:
    workout = _workout(distance=200, pool=50, pace=70.0, name="e2e-50m-200")
    profile = _continuous_profile(
        profile_id="e2e-pool50",
        pool=50,
        total_distance=200.0,
        target_time=160.0,
        knots=[(0.0, 1.25), (100.0, 1.25), (200.0, 1.25)],
    )
    scenario = SimulationScenario(
        scenarioId="e2e-50m-official-distance",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=workout,
        profile=profile,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        description="Phase 1 e2e: 50 m course official-distance authority.",
    )
    return Phase1E2ECase(
        caseId="fifty-metre-pool-official-distance",
        caseVersion=CASE_VERSION,
        seed=42,
        workout=workout,
        paceProfiles=(profile,),
        selectedProfileId=profile.profileId,
        scenario=scenario,
        expectedOutcome=Phase1ExpectedOutcome(
            officialDistanceM=200.0,
            poolLengthM=50,
            officialLengthCount=4,
            stoppedDurationMs=0,
        ),
        description=(
            "A 50 m course with a dive start: official distance starts at 0 m, the first "
            "length is exactly 50 m, and a mid-pool estimate never becomes an official split."
        ),
    )


# --------------------------------------------------------------------------- scenario-backed
def _scenario_case(
    *,
    case_id: str,
    scenario_id: str,
    expected: Phase1ExpectedOutcome,
    description: str,
    emit_observations: bool = False,
) -> Phase1E2ECase:
    scenario = SCENARIO_BY_NAME[scenario_id]()
    profiles = [scenario.profile]
    if scenario.replacementProfile is not None:
        profiles.append(scenario.replacementProfile)
    return Phase1E2ECase(
        caseId=case_id,
        caseVersion=CASE_VERSION,
        seed=scenario.defaultSeed,
        workout=scenario.workout,
        paceProfiles=tuple(profiles),
        selectedProfileId=scenario.profile.profileId,
        scenario=scenario,
        expectedOutcome=expected,
        description=description,
        failureScenarioId=scenario_id,
        emitObservations=emit_observations,
    )


def case_long_stop_and_reconciliation() -> Phase1E2ECase:
    return _scenario_case(
        case_id="long-stop-and-reconciliation",
        scenario_id="long-stop-mid-length",
        expected=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stopPauseCount=1,
            stoppedDurationMs=15_000,
        ),
        description=(
            "A 15 s mid-length stop confirmed 6 s late: the retroactive freeze holds, the "
            "mid-pool alignment never becomes official distance, and the next official wall "
            "reconciles exactly once."
        ),
    )


def case_coach_profile_reset() -> Phase1E2ECase:
    return _scenario_case(
        case_id="coach-profile-reset",
        scenario_id="coach-continuous-curve-reset",
        expected=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stoppedDurationMs=0,
            coachResetAppliedCount=1,
            finalProfileId="resetrepl100",
            finalProfileSource="COACH_APPROVED_MODEL",
            finalProfileCoachLocked=True,
        ),
        description=(
            "A mid-length coach curve reset applies at the next official wall, swaps the "
            "full profile metadata in live and replay state, keeps earlier split provenance "
            "on the previous profile and adds no stopped time."
        ),
    )


def case_complete_while_stop_paused() -> Phase1E2ECase:
    return _scenario_case(
        case_id="complete-while-stop-paused",
        scenario_id="complete-while-stop-paused",
        expected=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stopPauseCount=1,
            stoppedDurationMs=10_000,
            rejectedCommandCount=1,
        ),
        description=(
            "CompleteSession is rejected while a StopPause is open and appends nothing to "
            "the journal; after the resolve and the final official wall it succeeds."
        ),
    )


def case_duplicate_command_durability() -> Phase1E2ECase:
    return _scenario_case(
        case_id="duplicate-command-durability",
        scenario_id="duplicate-stop-mark",
        expected=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stopPauseCount=1,
            stoppedDurationMs=12_000,
            idempotentReplayCount=1,
        ),
        description=(
            "The identical command re-sent with the same clientCommandId produces no second "
            "domain event, no duplicate journal line and no sequence gap."
        ),
    )


def case_unreliable_observation_report() -> Phase1E2ECase:
    return _scenario_case(
        case_id="unreliable-observation-report",
        scenario_id="unreliable-position-time",
        expected=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stoppedDurationMs=0,
            continuousCurveAvailable=False,
        ),
        description=(
            "A low-confidence position window keeps official distance intact, leaves the "
            "continuous curve unavailable rather than fabricating one, and split analytics "
            "continue from official walls."
        ),
        emit_observations=True,
    )


def case_normal_pace_loss() -> Phase1E2ECase:
    return _scenario_case(
        case_id="normal-pace-loss",
        scenario_id="normal-pace-loss",
        expected=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stoppedDurationMs=0,
            datasetEvidenceAssetIds=(
                "adaptive_swim_unified_official_pacing_all_sources_v3",
                "adaptive_swim_training_fatigue_weekly_and_repeat_model_ready_v1",
            ),
            requireNotGroundTruth=True,
        ),
        description=(
            "A genuine, persistent pace loss produces no StopPause and no stopped duration; "
            "the ghost and the ActiveClock keep running."
        ),
    )


def case_manual_stop_at_verified_wall() -> Phase1E2ECase:
    return _scenario_case(
        case_id="manual-stop-at-verified-wall",
        scenario_id="manual-stop-at-verified-wall",
        expected=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stopPauseCount=1,
            stoppedDurationMs=12_000,
        ),
        description=(
            "A manual coach-marked stop at a verified wall aligns from official geometry, "
            "never from a mid-pool estimate, and is not a lifecycle pause."
        ),
    )


def case_stop_during_planned_rest() -> Phase1E2ECase:
    return _scenario_case(
        case_id="stop-during-planned-rest",
        scenario_id="stop-during-planned-rest",
        expected=Phase1ExpectedOutcome(
            officialDistanceM=100.0,
            poolLengthM=25,
            officialLengthCount=4,
            stoppedDurationMs=0,
        ),
        description=(
            "Scheduled rest is not a StopPause: no stop event is emitted, stopped duration "
            "stays zero and no synthetic lifecycle state is invented."
        ),
    )


#: The ten required Phase 1 closure cases, in canonical order.
REQUIRED_CASES: tuple[Callable[[], Phase1E2ECase], ...] = (
    case_normal_continuous_completion,
    case_legacy_profile_compatibility,
    case_migrated_profile_equivalence,
    case_long_stop_and_reconciliation,
    case_coach_profile_reset,
    case_complete_while_stop_paused,
    case_duplicate_command_durability,
    case_unreliable_observation_report,
    case_dataset_evidence_provenance,
    case_fifty_metre_pool_official_distance,
)

#: The remaining required Commit 8 failure scenarios, run end to end here as well.
FAILURE_SCENARIO_CASES: tuple[Callable[[], Phase1E2ECase], ...] = (
    case_normal_pace_loss,
    case_manual_stop_at_verified_wall,
    case_stop_during_planned_rest,
)

ALL_CASES: tuple[Callable[[], Phase1E2ECase], ...] = REQUIRED_CASES + FAILURE_SCENARIO_CASES

CASE_BY_ID: dict[str, Callable[[], Phase1E2ECase]] = {
    builder().caseId: builder for builder in ALL_CASES
}

REQUIRED_CASE_IDS: tuple[str, ...] = tuple(builder().caseId for builder in REQUIRED_CASES)

#: Every required Commit 8 failure scenario must be covered by the e2e matrix.
COVERED_FAILURE_SCENARIOS: tuple[str, ...] = tuple(
    sorted(
        {
            scenario_id
            for scenario_id in (builder().failureScenarioId for builder in ALL_CASES)
            if scenario_id is not None
        }
    )
)


def build_all_cases() -> list[Phase1E2ECase]:
    return [builder() for builder in ALL_CASES]


__all__ = [
    "ALL_CASES",
    "CASE_BY_ID",
    "CASE_VERSION",
    "COVERED_FAILURE_SCENARIOS",
    "FAILURE_SCENARIO_CASES",
    "REQUIRED_CASES",
    "REQUIRED_CASE_IDS",
    "build_all_cases",
]
