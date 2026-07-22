from __future__ import annotations

from analytics import ProfileRuntimeContext, ReportBuildContext, build_session_report
from simulator.harness import SimulationResult, compile_ghost_timeline
from simulator.scenarios import SCENARIO_BY_NAME


def test_report_builder_is_replay_based_and_deterministic(
    normal_report_result: SimulationResult,
) -> None:
    scenario = SCENARIO_BY_NAME["normal-pace-loss"]()
    timeline = compile_ghost_timeline(scenario.profile, scenario.workout)
    context = ReportBuildContext(
        simulatorSynthetic=True,
        simulationRunId=normal_report_result.runId,
        profileRegistry={
            (scenario.profile.profileId, scenario.profile.profileVersion): ProfileRuntimeContext(
                scenario.profile, timeline
            )
        },
    )
    rebuilt = build_session_report(
        replay_state=normal_report_result.replayResult.state,
        events=normal_report_result.events,
        workout=scenario.workout,
        pace_profile=scenario.profile,
        compiled_timeline=timeline,
        observations=(),
        report_context=context,
    )
    # Observation inputs are part of the content-addressed identity.  Rebuilding without
    # simulator observations must therefore produce a different reportId.
    assert rebuilt.reportId != normal_report_result.sessionReport.reportId
    assert (
        rebuilt.provenance.eventDigestSha256
        == normal_report_result.sessionReport.provenance.eventDigestSha256
    )
    assert rebuilt.continuousCurveAnalysis.available is False
