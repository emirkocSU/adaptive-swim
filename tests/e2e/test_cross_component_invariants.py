"""The cross-component invariant matrix is authoritative and complete (ADR-041 §8)."""

from __future__ import annotations

import pytest

from e2e.manifest import CheckStatus
from e2e.types import Phase1E2EResult

_GROUPS = ("event.", "state.", "clock.", "distance.", "profile.", "report.", "case.")


@pytest.mark.parametrize("group", _GROUPS)
def test_every_invariant_group_is_present(
    group: str, all_results: dict[str, Phase1E2EResult]
) -> None:
    for result in all_results.values():
        ids = [check.checkId for check in result.verificationManifest.checks]
        assert any(check_id.startswith(group) for check_id in ids), (
            f"{result.caseId} has no {group} invariants"
        )


def test_no_check_ever_fails(all_results: dict[str, Phase1E2EResult]) -> None:
    for result in all_results.values():
        failed = [
            check.checkId
            for check in result.verificationManifest.checks
            if check.status is CheckStatus.FAIL
        ]
        assert failed == [], f"{result.caseId}: {failed}"


def test_event_invariants(all_results: dict[str, Phase1E2EResult]) -> None:
    for result in all_results.values():
        manifest = result.verificationManifest
        assert manifest.eventFirstSeq == 1
        assert manifest.eventLastSeq == manifest.eventCount
        flattened = [seq for batch in result.eventBatches for seq in batch]
        assert flattened == sorted(flattened)
        assert len(set(flattened)) == len(flattened)
        assert flattened == list(range(1, manifest.eventCount + 1))
        assert manifest.batchCount == len(result.eventBatches)


def test_live_and_replay_state_agree(all_results: dict[str, Phase1E2EResult]) -> None:
    for result in all_results.values():
        live, replay = result.liveFinalState, result.replayFinalState
        assert result.liveReplayMatch
        assert live.lifecycleState == replay.lifecycleState.value
        assert live.officialCompletedDistanceM == replay.officialCompletedDistanceM
        assert live.selectedPaceProfileId == replay.selectedPaceProfileId
        assert live.selectedPaceProfileSource == replay.selectedPaceProfileSource
        assert live.profileCoachLocked == replay.profileCoachLocked
        assert live.activeDurationMs == replay.activeDurationMs
        assert live.stoppedDurationMs == replay.stoppedDurationMs
        assert live.wallElapsedMs == replay.wallDurationMs


def test_clock_axes_stay_separate(all_results: dict[str, Phase1E2EResult]) -> None:
    for result in all_results.values():
        state = result.replayFinalState
        assert state.activeDurationMs >= 0
        assert state.stoppedDurationMs >= 0
        assert state.lifecyclePausedDurationMs >= 0
        assert state.elapsedDurationMs == state.activeDurationMs + state.stoppedDurationMs
        assert state.wallDurationMs == state.elapsedDurationMs + state.lifecyclePausedDurationMs
        interval_total = sum(item.durationMs or 0 for item in state.completedStopPauses)
        assert interval_total == state.stoppedDurationMs


def test_pace_loss_and_coach_reset_create_no_stopped_time(
    all_results: dict[str, Phase1E2EResult],
) -> None:
    for case_id in ("normal-pace-loss", "coach-profile-reset", "stop-during-planned-rest"):
        state = all_results[case_id].replayFinalState
        assert state.stoppedDurationMs == 0
        assert state.completedStopPauses == ()


def test_official_distance_invariants(all_results: dict[str, Phase1E2EResult]) -> None:
    for result in all_results.values():
        state = result.replayFinalState
        pool = state.poolLengthM
        assert pool is not None
        assert state.officialCompletedDistanceM == state.officialCompletedLengthCount * pool
        planned = result.sessionReport.distanceSummary.plannedDistanceM
        assert planned is not None
        assert state.officialCompletedDistanceM is not None
        assert state.officialCompletedDistanceM <= planned + 1e-9
        indices = [split.lengthIndex for split in state.recordedSplits]
        assert len(set(indices)) == len(indices)


def test_report_invariants(all_results: dict[str, Phase1E2EResult]) -> None:
    for result in all_results.values():
        report = result.sessionReport
        assert report.sessionId == result.replayFinalState.sessionId
        assert report.createdFromLastSeq == result.replayFinalState.lastSeq
        assert report.reportGeneratedAtMs == result.replayFinalState.lastEventTimestampMs
        assert report.provenance.paceProfileId == result.replayFinalState.selectedPaceProfileId
        aggregate = report.splitAnalysis.aggregate
        if aggregate.eligibleSplitCount == 0:
            assert aggregate.meanAbsoluteSplitErrorSec is None
            assert aggregate.targetPaceAdherenceRatio is None
        curve = report.continuousCurveAnalysis
        if not curve.available:
            assert curve.curveDeviationMean is None
            assert curve.curveDeviationRms is None


def test_target_and_forecast_stay_separate(all_results: dict[str, Phase1E2EResult]) -> None:
    for result in all_results.values():
        context = result.sessionReport.paceProfileContext
        assert context.predictedSplitTimesSec is None
        assert context.predictedNextRepeatTimeSec is None
        assert context.predictedNextSplitTimeSec is None
        if context.status.value == "AVAILABLE":
            assert context.targetTotalTimeSec is not None


def test_dataset_evidence_is_not_performance_evidence(
    all_results: dict[str, Phase1E2EResult],
) -> None:
    for result in all_results.values():
        provenance = result.sessionReport.provenance
        assert provenance.simulatorSynthetic is True
        assert provenance.continuousCurveGroundTruth is not True
        assert "SYNTHETIC_NOT_PERFORMANCE_EVIDENCE" in result.sessionReport.dataQuality.warningCodes
