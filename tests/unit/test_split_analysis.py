from __future__ import annotations

from analytics import ReportBuildContext, build_session_report
from tests.unit._analytics_helpers import case, report


def test_split_target_actual_delta_and_aggregates() -> None:
    result = report((20_000, 41_000, 61_000, 82_000))
    assert result.splitAnalysis.splits[1].durationDeltaSec == 1
    assert result.splitAnalysis.aggregate.meanAbsoluteSplitErrorSec == 0.5
    assert result.splitAnalysis.aggregate.eligibleSplitCount == 4


def test_missing_target_produces_none_not_zero() -> None:
    wk, _profile, events, state, _timeline = case()
    result = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=None,
        compiled_timeline=None,
        report_context=ReportBuildContext(),
    )
    assert result.splitAnalysis.splits[0].targetDurationSec is None
    assert result.splitAnalysis.splits[0].targetStatus.value == "MISSING_TARGET"
