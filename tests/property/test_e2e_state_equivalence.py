"""Property-based live/replay/report equivalence for Phase 1 (ADR-041 §19)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from e2e.cases import CASE_BY_ID
from e2e.runner import run_phase1_vertical_slice

_CASES = (
    "normal-continuous-completion",
    "stop-during-planned-rest",
    "long-stop-and-reconciliation",
)


@given(st.sampled_from(_CASES))
@settings(max_examples=3, deadline=None)
def test_live_replay_and_report_always_agree(case_id: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        result = run_phase1_vertical_slice(
            case=CASE_BY_ID[case_id](), output_directory=Path(directory) / "bundle"
        )
    live, replay, report = result.liveFinalState, result.replayFinalState, result.sessionReport
    # live == replay
    assert result.liveReplayMatch
    assert live.lifecycleState == replay.lifecycleState.value
    assert live.activeDurationMs == replay.activeDurationMs
    assert live.stoppedDurationMs == replay.stoppedDurationMs
    # report == replay
    assert report.sessionId == replay.sessionId
    assert report.createdFromLastSeq == replay.lastSeq
    assert report.distanceSummary.officialCompletedDistanceM == replay.officialCompletedDistanceM
    # official distance stays pool-compatible and bounded by the plan
    pool = replay.poolLengthM
    planned = report.distanceSummary.plannedDistanceM
    assert pool is not None and planned is not None
    assert replay.officialCompletedDistanceM is not None
    assert replay.officialCompletedDistanceM % pool == 0
    assert replay.officialCompletedDistanceM <= planned + 1e-9
    # durations are non-negative and consistent
    assert replay.activeDurationMs >= 0
    assert replay.stoppedDurationMs >= 0
    assert replay.elapsedDurationMs == replay.activeDurationMs + replay.stoppedDurationMs


@given(st.sampled_from(_CASES))
@settings(max_examples=2, deadline=None)
def test_no_raw_dataset_path_ever_appears_in_an_artifact(case_id: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        result = run_phase1_vertical_slice(
            case=CASE_BY_ID[case_id](), output_directory=Path(directory) / "bundle"
        )
        for path in sorted(result.bundleDirectory.iterdir()):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("data/external/raw", ".csv", ".zip"):
                assert forbidden not in text, f"{path.name} leaks {forbidden}"
