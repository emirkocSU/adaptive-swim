from __future__ import annotations

from simulator.harness import SimulationResult


def test_all_eight_scenarios_emit_canonical_reports(
    analytics_results: dict[str, SimulationResult],
) -> None:
    assert len(analytics_results) == 8
    for result in analytics_results.values():
        assert result.sessionReportPath.read_bytes() == result.sessionReportBytes
        assert len(result.sessionReportSha256) == 64
        assert result.sessionReport.provenance.simulatorSynthetic is True
        assert result.sessionReport.provenance.simulationRunId == result.runId


def test_required_scenario_acceptance(
    analytics_results: dict[str, SimulationResult],
) -> None:
    normal = analytics_results["normal-pace-loss"].sessionReport
    assert normal.stopPauseAnalysis.stopPauseCount == 0
    assert any(split.aheadBehindStatus.value == "BEHIND" for split in normal.splitAnalysis.splits)

    stopped = analytics_results["long-stop-mid-length"].sessionReport
    assert stopped.stopPauseAnalysis.stopPauseCount == 1
    assert stopped.stopPauseAnalysis.totalStoppedDurationMs > 0
    assert (
        stopped.distanceSummary.officialCompletedDistanceM
        == stopped.distanceSummary.plannedDistanceM
    )

    manual = analytics_results["manual-stop-at-verified-wall"].sessionReport
    assert manual.stopPauseAnalysis.manualStopCount == 1

    duplicate = analytics_results["duplicate-stop-mark"].sessionReport
    assert duplicate.stopPauseAnalysis.stopPauseCount == 1

    rest = analytics_results["stop-during-planned-rest"].sessionReport
    assert rest.stopPauseAnalysis.stopPauseCount == 0
    assert rest.timingSummary.stoppedDurationMs == 0

    unreliable = analytics_results["unreliable-position-time"].sessionReport
    assert unreliable.continuousCurveAnalysis.available is False
    assert unreliable.continuousCurveAnalysis.status.value == "LOW_QUALITY"

    complete = analytics_results["complete-while-stop-paused"].sessionReport
    assert complete.sessionSummary.lifecycleState == "COMPLETED"
    assert complete.stopPauseAnalysis.resolvedStopCount == 1

    reset = analytics_results["coach-continuous-curve-reset"].sessionReport
    assert reset.coachResetAnalysis.coachResetRequestedCount == 1
    assert reset.coachResetAnalysis.coachResetAppliedCount == 1
    assert reset.coachResetAnalysis.safeWallApplicationCount == 1
    ids = [split.profileId for split in reset.splitAnalysis.splits]
    assert ids[:2] == ["resetbase100", "resetbase100"]
    assert ids[2:] == ["resetrepl100", "resetrepl100"]
    assert reset.timingSummary.stoppedDurationMs == 0
