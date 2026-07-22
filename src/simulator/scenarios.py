"""Deterministic scenario library for the headless simulator (Commit 8, corrected).

The EIGHT required acceptance scenarios (§2.1) — exact CLI slugs, no aliases:

    normal-pace-loss              swimmer genuinely behind the target curve (no StopPause)
    long-stop-mid-length          retroactive freeze, mid-pool alignment, one reconciliation
    manual-stop-at-verified-wall  manual trigger, official-wall alignment, no mid-pool estimate
    duplicate-stop-mark           identical MarkStopPause twice → zero new events/batches
    stop-during-planned-rest      schedule-level rest; no StopPause; stoppedDuration stays 0
    unreliable-position-time      low position confidence is VISUAL only; official distance holds
    complete-while-stop-paused    CompleteSession rejected while open; succeeds after resolve
    coach-continuous-curve-reset  mid-length request, next-wall apply, full metadata swap

The old demo scenarios are retained BELOW as helper examples only — they are not part of
the acceptance set and no required slug aliases to them.

Every scenario embeds a registry default seed; the CLI ``--seed`` overrides it and feeds
the real virtual-swimmer RNG (§2.2).
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
    AlignmentSource,
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
    StopDetectionSource,
    StopPauseTrigger,
    Stroke,
    TargetTimeSource,
    VisualShapeSource,
    WorkoutGoal,
)
from contracts.pace_profiles import ApprovedPaceProfile, PaceProfileLeg
from contracts.workout import WorkoutTemplateV1_1
from simulator.harness import (
    ScenarioStop,
    SimulationScenario,
    SwimmerParams,
)
from simulator.virtual_swimmer import RestWindow, UnreliableWindow

_POOL = 25

#: Version of the required-scenario semantics (part of the deterministic runId).
SCENARIO_SET_VERSION = "2.0.0"


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
    coach_locked: bool = False,
    provenance: CurveProvenance | None = None,
) -> ApprovedContinuousPaceProfile:
    return ApprovedContinuousPaceProfile(
        profileId=profile_id,
        profileVersion="1",
        source=source,
        profileType=profile_type,
        approvalStatus=ProfileApprovalStatus.COACH_APPROVED,
        coachLocked=coach_locked,
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
        curveProvenance=(
            provenance
            if provenance is not None
            else CurveProvenance(
                generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
                targetTimeSource=TargetTimeSource.COACH,
            )
        ),
    )


#: Dataset-evidence provenance for the normal-pace-loss fixture profile (§13): an
#: operational target-envelope shaped by a race prior + training correction. It is a
#: bounded template — NEVER measured continuous velocity (continuousCurveGroundTruth=False).
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
    sourceDatasetManifestVersions=("1.0.0", "1.0.0"),
)


# =========================================================================================
# The EIGHT required acceptance scenarios (§2.1)
# =========================================================================================
def scenario_normal_pace_loss() -> SimulationScenario:
    """Swimmer genuinely behind the target curve: gap grows and persists; NO StopPause."""
    wk = _workout(100)
    prof = _pchip_profile(
        "normal100",
        100.0,
        80.0,
        [(0.0, 1.28), (50.0, 1.25), (100.0, 1.22)],
        provenance=_DATASET_EVIDENCE_PROVENANCE,
    )
    return SimulationScenario(
        scenarioId="normal-pace-loss",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(baseResponseRatio=0.90, noiseStdMps=0.01, turnDelayMs=300),
        description=(
            "100 m continuous curve; swimmer responds at 90% of target so the gap grows "
            "and persists. Ghost and ActiveClock continue; no StopPause, no incident."
        ),
    )


def scenario_long_stop_mid_length() -> SimulationScenario:
    """Long stop mid-length: retroactive freeze; mid-pool alignment; single reconciliation."""
    wk = _workout(100)
    prof = _pchip_profile("longstop100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    return SimulationScenario(
        scenarioId="long-stop-mid-length",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        stop=ScenarioStop(
            afterLengthIndex=1,
            offsetAfterWallMs=4000,  # genuinely mid-length
            durationMs=15_000,
            trackedAlignmentDistanceM=60.0,  # mid-pool tracked estimate (visual only)
            confirmDelayMs=6000,  # stop starts meaningfully BEFORE its confirmation
            alignmentSource=AlignmentSource.TRACKED_POSITION,
        ),
        description=(
            "100 m with a 15 s stop starting mid-length, confirmed 6 s later (retroactive "
            "freeze); tracked mid-pool alignment is visual only; the next official wall "
            "reconciles exactly once."
        ),
    )


def scenario_manual_stop_at_verified_wall() -> SimulationScenario:
    """Manual stop AT a verified wall: official-wall alignment; no mid-pool estimate."""
    wk = _workout(100)
    prof = _pchip_profile("manualstop100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    return SimulationScenario(
        scenarioId="manual-stop-at-verified-wall",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        stop=ScenarioStop(
            afterLengthIndex=1,
            offsetAfterWallMs=0,  # the stop happens AT the wall
            durationMs=12_000,
            trackedAlignmentDistanceM=50.0,  # the official wall, not a mid-pool estimate
            trigger=StopPauseTrigger.MANUAL_INCIDENT,
            detectionSource=StopDetectionSource.COACH,
            alignmentSource=AlignmentSource.COACH_MARK,
            confirmDelayMs=1,
            atWallBeforeSplit=True,
        ),
        description=(
            "100 m with a manual coach-marked stop at the verified 50 m wall; alignment "
            "comes from the official wall; StopPause is not a lifecycle pause."
        ),
    )


def scenario_duplicate_stop_mark() -> SimulationScenario:
    """The identical MarkStopPause sent twice: second → zero events, one journal batch."""
    wk = _workout(100)
    prof = _pchip_profile("dupstop100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    return SimulationScenario(
        scenarioId="duplicate-stop-mark",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        stop=ScenarioStop(
            afterLengthIndex=1,
            offsetAfterWallMs=3000,
            durationMs=12_000,
            trackedAlignmentDistanceM=58.0,
            confirmDelayMs=2000,
            duplicateMark=True,
        ),
        description=(
            "Same clientCommandId + identical MarkStopPause twice: the second command "
            "produces zero events; exactly one open interval and one journal batch."
        ),
    )


def scenario_stop_during_planned_rest() -> SimulationScenario:
    """Planned rest at the SCHEDULE level: no StopPause; stoppedDuration stays zero."""
    wk = _workout(100)
    prof = _pchip_profile("rest100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    return SimulationScenario(
        scenarioId="stop-during-planned-rest",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        rest=RestWindow(afterLengthIndex=1, durationMs=20_000),
        description=(
            "The swimmer stops during an explicitly scheduled 20 s rest after the 50 m "
            "wall. The rest is modeled at the simulator schedule level only: no StopPause "
            "event, stoppedDuration does not grow, no fake lifecycle state in the core."
        ),
    )


def scenario_unreliable_position_time() -> SimulationScenario:
    """Low position/time confidence: estimated position is visual only; wall reconciles."""
    wk = _workout(100)
    prof = _pchip_profile("unreliable100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    return SimulationScenario(
        scenarioId="unreliable-position-time",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        unreliable=UnreliableWindow(
            afterLengthIndex=1, offsetAfterWallMs=1000, durationMs=15_000, positionNoiseM=3.0
        ),
        description=(
            "A 15 s window of LOW position/time confidence mid-swim: the noisy estimated "
            "position stays a visual observation only; official distance and completed "
            "length counts never change; the next verified wall reconciles."
        ),
    )


def scenario_complete_while_stop_paused() -> SimulationScenario:
    """CompleteSession during an open StopPause is rejected; succeeds after resolve."""
    wk = _workout(100)
    prof = _pchip_profile("completestop100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    return SimulationScenario(
        scenarioId="complete-while-stop-paused",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        stop=ScenarioStop(
            afterLengthIndex=2,
            offsetAfterWallMs=2500,
            durationMs=10_000,
            trackedAlignmentDistanceM=82.0,
            confirmDelayMs=2000,
        ),
        attemptCompleteWhileStopPaused=True,
        description=(
            "While the StopPause is open, CompleteSession is rejected and neither the "
            "aggregate, the EventFactory sequence nor the journal changes. After the "
            "resolve and the official final wall, CompleteSession succeeds."
        ),
    )


def scenario_coach_continuous_curve_reset() -> SimulationScenario:
    """Mid-length coach reset; applied only at the next official wall; full metadata swap."""
    wk = _workout(100)
    prof = _pchip_profile("resetbase100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    replacement = _pchip_profile(
        "resetrepl100",
        100.0,
        100.0,
        [(0.0, 1.0), (100.0, 1.0)],
        source=PaceProfileSource.COACH_APPROVED_MODEL,
        profile_type=PaceProfileType.CONTROLLED_START,
        coach_locked=True,
    )
    return SimulationScenario(
        scenarioId="coach-continuous-curve-reset",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=42,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(noiseStdMps=0.005),
        replacementProfile=replacement,
        replacementAfterLengthIndex=1,
        description=(
            "Coach requests a continuous-curve reset mid-length; the coach-locked "
            "COACH_APPROVED_MODEL replacement is applied only at the next official wall. "
            "No StopPause, stoppedDuration unchanged, past split history preserved, and "
            "live + replay both show the full replacement profile metadata."
        ),
    )


# =========================================================================================
# Legacy demo scenarios (helper examples only — NOT the acceptance set; no alias maps to
# them from the required slugs)
# =========================================================================================
def scenario_even_on_plan() -> SimulationScenario:
    wk = _workout(100)
    prof = _pchip_profile("even100", 100.0, 80.0, [(0.0, 1.25), (100.0, 1.25)])
    return SimulationScenario(
        scenarioId="even-on-plan",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=1001,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(baseResponseRatio=1.0),
        description="[demo] 100 m even PCHIP curve, swimmer exactly on plan.",
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
    return SimulationScenario(
        scenarioId="negative-split",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=1002,
        workout=wk,
        profile=prof,
        swimmer=SwimmerParams(noiseStdMps=0.01),
        description="[demo] 200 m negative-split PCHIP with small deterministic noise.",
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
    return SimulationScenario(
        scenarioId="positive-fade",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=1003,
        workout=wk,
        profile=prof,
        # a natural sprint fade — the swimmer slows with distance (not an incident)
        swimmer=SwimmerParams(fatigueSlopePer100M=0.06),
        description="[demo] 100 m sprint with a natural positive split / fade (no incident).",
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
    return SimulationScenario(
        scenarioId="locked-splits",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=1004,
        workout=wk,
        profile=prof,
        description="[demo] 100 m curve with a coach-locked first 50 m split (42 s of 80 s).",
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
    return SimulationScenario(
        scenarioId="migrated-legacy",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=1007,
        workout=_workout(100),
        profile=migrated,
        description="[demo] Legacy 1.0 profile migrated to a 1.1 constant-speed curve.",
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
    return SimulationScenario(
        scenarioId="constant-speed-template",
        scenarioVersion=SCENARIO_SET_VERSION,
        defaultSeed=1008,
        workout=wk,
        profile=prof,
        description="[demo] Explicit CONSTANT_SPEED template curve (non-migration path).",
    )


#: The eight REQUIRED acceptance scenarios (§2.1), in canonical order.
REQUIRED_SCENARIOS = (
    scenario_normal_pace_loss,
    scenario_long_stop_mid_length,
    scenario_manual_stop_at_verified_wall,
    scenario_duplicate_stop_mark,
    scenario_stop_during_planned_rest,
    scenario_unreliable_position_time,
    scenario_complete_while_stop_paused,
    scenario_coach_continuous_curve_reset,
)

#: Legacy demo scenarios (helper examples only).
DEMO_SCENARIOS = (
    scenario_even_on_plan,
    scenario_negative_split,
    scenario_positive_fade,
    scenario_locked_splits,
    scenario_migrated_legacy,
    scenario_constant_speed_template,
)

#: Ordered scenario builders (required first). Stable ordering for golden generation.
ALL_SCENARIOS = REQUIRED_SCENARIOS + DEMO_SCENARIOS

SCENARIO_BY_NAME = {builder().scenarioId: builder for builder in ALL_SCENARIOS}

REQUIRED_SCENARIO_NAMES = tuple(builder().scenarioId for builder in REQUIRED_SCENARIOS)


def build_all_scenarios() -> list[SimulationScenario]:
    return [builder() for builder in ALL_SCENARIOS]
