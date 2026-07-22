"""Every required Phase 1 case and every required failure scenario runs end to end."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from e2e.cases import CASE_BY_ID, COVERED_FAILURE_SCENARIOS, REQUIRED_CASE_IDS, build_all_cases
from e2e.manifest import CheckStatus
from e2e.types import Phase1E2EResult
from simulator.scenarios import REQUIRED_SCENARIO_NAMES

_ALL_CASE_IDS = [case.caseId for case in build_all_cases()]

_REQUIRED = (
    "normal-continuous-completion",
    "legacy-profile-compatibility",
    "migrated-profile-equivalence",
    "long-stop-and-reconciliation",
    "coach-profile-reset",
    "complete-while-stop-paused",
    "duplicate-command-durability",
    "unreliable-observation-report",
    "dataset-evidence-provenance",
    "fifty-metre-pool-official-distance",
)


def test_ten_required_cases_exist() -> None:
    assert REQUIRED_CASE_IDS == _REQUIRED
    assert len(REQUIRED_CASE_IDS) >= 10


def test_every_required_failure_scenario_is_covered_end_to_end() -> None:
    assert set(COVERED_FAILURE_SCENARIOS) == set(REQUIRED_SCENARIO_NAMES)
    assert len(COVERED_FAILURE_SCENARIOS) == 8


@pytest.mark.parametrize("case_id", _ALL_CASE_IDS)
def test_case_passes_all_checks(case_id: str, run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case(case_id)
    failures = [
        check.checkId
        for check in result.verificationManifest.checks
        if check.status is CheckStatus.FAIL
    ]
    assert failures == []
    assert result.allChecksPassed
    assert result.verificationManifest.allChecksPassed


def test_case_one_normal_continuous(run_case: Callable[..., Phase1E2EResult]) -> None:
    state = run_case("normal-continuous-completion").replayFinalState
    assert state.officialCompletedDistanceM == 100.0
    assert state.stoppedDurationMs == 0
    assert not state.completedStopPauses


def test_case_two_legacy_profile_uses_the_legacy_compiler(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case("legacy-profile-compatibility")
    assert result.sessionReport.provenance.paceProfileSchemaVersion == "1.0"
    assert result.replayFinalState.selectedCurveRepresentation is None
    assert result.sessionReport.splitAnalysis.status.value == "AVAILABLE"


def test_legacy_case_executes_a_real_workout_1_0_source(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    case = CASE_BY_ID["legacy-profile-compatibility"]()
    assert case.sourceWorkoutV1_0 is not None
    assert case.sourceWorkoutV1_0.schemaVersion == "1.0"
    result = run_case("legacy-profile-compatibility")
    assert result.sourceWorkoutDigest is not None
    assert result.verificationManifest.sourceWorkoutDigest == result.sourceWorkoutDigest
    assert result.sessionReport.provenance.workoutSchemaVersion == "1.1"


def test_case_three_migration_equivalence(run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case("migrated-profile-equivalence")
    migration = [
        check
        for check in result.verificationManifest.checks
        if check.checkId.startswith("migration.")
    ]
    assert migration
    assert all(check.status is CheckStatus.PASS for check in migration)
    ids = {check.checkId for check in migration}
    assert {
        "migration.command_outcomes_equivalent",
        "migration.journal_semantics_equivalent",
        "migration.journal_batch_structure_equivalent",
        "migration.live_session_output_equivalent",
        "migration.replay_state_equivalent",
        "migration.report_output_equivalent",
    } <= ids


def test_case_four_long_stop(run_case: Callable[..., Phase1E2EResult]) -> None:
    report = run_case("long-stop-and-reconciliation").sessionReport
    assert report.stopPauseAnalysis.stopPauseCount == 1
    assert report.stopPauseAnalysis.totalStoppedDurationMs == 15_000
    assert report.stopPauseAnalysis.wallReconciliationCount == 1
    assert report.stopPauseAnalysis.pendingWallReconciliationCount == 0
    assert report.distanceSummary.officialCompletedDistanceM == 100.0


def test_case_five_coach_reset(run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case("coach-profile-reset")
    report = result.sessionReport
    assert report.coachResetAnalysis.coachResetAppliedCount == 1
    assert report.paceProfileContext.paceProfileId == "resetrepl100"
    assert report.paceProfileContext.coachLocked is True
    assert report.stopPauseAnalysis.totalStoppedDurationMs == 0
    reset_wall = report.coachResetAnalysis.resets[0].appliedWallDistanceM
    assert reset_wall is not None
    before = [s for s in report.splitAnalysis.splits if s.toM <= reset_wall]
    after = [s for s in report.splitAnalysis.splits if s.fromM >= reset_wall]
    assert before and after
    assert all(split.profileId == "resetbase100" for split in before)
    assert all(split.profileId == "resetrepl100" for split in after)


def test_case_six_complete_while_stop_paused(run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case("complete-while-stop-paused")
    rejected = [o for o in result.commandOutcomes if o.outcome == "REJECTED"]
    assert len(rejected) == 1
    assert rejected[0].eventCount == 0
    assert result.replayFinalState.lifecycleState.value == "COMPLETED"


def test_case_seven_duplicate_command(run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case("duplicate-command-durability")
    replays = [o for o in result.commandOutcomes if o.outcome == "IDEMPOTENT_REPLAY"]
    assert len(replays) == 1
    assert replays[0].eventCount == 0
    assert result.verificationManifest.batchCount == len(result.eventBatches)


def test_case_eight_unreliable_observations(run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case("unreliable-observation-report")
    curve = result.sessionReport.continuousCurveAnalysis
    assert curve.available is False
    assert curve.curveDeviationMean is None
    assert result.replayFinalState.officialCompletedDistanceM == 100.0
    assert result.sessionReport.splitAnalysis.status.value == "AVAILABLE"
    assert result.observationsPath is not None and result.observationsPath.is_file()


def test_case_nine_dataset_evidence(run_case: Callable[..., Phase1E2EResult]) -> None:
    provenance = run_case("dataset-evidence-provenance").sessionReport.provenance
    assert provenance.curveOrigin == "RACE_PRIOR_TRAINING_CORRECTED"
    assert provenance.curveEvidenceLevel == "COARSE_SPLIT_DERIVED"
    assert provenance.visualShapeSource == "BOUNDED_TEMPLATE"
    assert provenance.continuousCurveGroundTruth is False
    assert len(provenance.datasetEvidenceAssetIds) == 2


def test_case_ten_fifty_metre_pool(run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case("fifty-metre-pool-official-distance")
    state = result.replayFinalState
    assert state.poolLengthM == 50
    assert state.officialCompletedLengthCount == 4
    assert state.officialCompletedDistanceM == 200.0
    first = result.sessionReport.splitAnalysis.splits[0]
    assert first.fromM == 0.0
    assert first.toM == 50.0
    assert first.distanceM == 50.0
