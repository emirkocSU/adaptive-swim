"""The Phase 1 vertical slice runs the real components end to end (ADR-041)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from analytics.serialization import encode_session_report
from e2e.manifest import CheckStatus
from e2e.types import (
    BUNDLE_COMMAND_OUTCOMES_FILE,
    BUNDLE_JOURNAL_FILE,
    BUNDLE_MANIFEST_FILE,
    BUNDLE_REPORT_FILE,
    BUNDLE_SHA256_FILE,
    Phase1E2EResult,
)
from persistence.jsonl_event_log import JsonlSessionEventLog
from swimcore.replay.reducer import replay_session
from swimcore.session.state import SessionState

CASE = "normal-continuous-completion"


def test_slice_completes_and_passes_every_invariant(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case(CASE)
    assert result.allChecksPassed
    assert not [
        check for check in result.verificationManifest.checks if check.status is CheckStatus.FAIL
    ]
    assert result.replayFinalState.lifecycleState is SessionState.COMPLETED


def test_bundle_contains_exactly_the_canonical_members(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case(CASE)
    names = sorted(path.name for path in result.bundleDirectory.iterdir())
    assert names == sorted(
        [
            BUNDLE_SHA256_FILE,
            BUNDLE_COMMAND_OUTCOMES_FILE,
            BUNDLE_JOURNAL_FILE,
            BUNDLE_MANIFEST_FILE,
            BUNDLE_REPORT_FILE,
        ]
    )


def test_journal_is_the_authoritative_input_of_the_report(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    """The report must be reproducible from the persisted journal alone."""
    result = run_case(CASE)
    events = (
        JsonlSessionEventLog(result.journalPath, result.replayFinalState.sessionId)
        .read_all()
        .events
    )
    replayed = replay_session(events, expected_session_id=result.replayFinalState.sessionId)
    assert replayed.state == result.replayFinalState
    assert result.sessionReport.createdFromLastSeq == events[-1].seq
    assert encode_session_report(result.sessionReport) == result.sessionReportPath.read_bytes()


def test_official_distance_comes_from_pool_geometry(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case(CASE)
    state = result.replayFinalState
    assert state.poolLengthM == 25
    assert state.officialCompletedDistanceM == 100.0
    assert state.officialCompletedLengthCount == 4
    for split in state.recordedSplits:
        assert split.officialDistanceM == (split.lengthIndex + 1) * 25


def test_report_reflects_targets_and_actuals(run_case: Callable[..., Phase1E2EResult]) -> None:
    result = run_case(CASE)
    report = result.sessionReport
    assert report.sessionSummary.completionStatus.value == "COMPLETED"
    assert report.splitAnalysis.status.value == "AVAILABLE"
    assert len(report.splitAnalysis.splits) == 4
    for split in report.splitAnalysis.splits:
        assert split.targetDurationSec is not None
        assert split.actualDurationSec > 0
    assert report.stopPauseAnalysis.stopPauseCount == 0
    assert report.provenance.simulatorSynthetic is True


def test_output_directory_never_leaks_into_artifacts(
    run_case: Callable[..., Phase1E2EResult], e2e_root: Path
) -> None:
    result = run_case(CASE)
    root = str(e2e_root)
    for name in (BUNDLE_MANIFEST_FILE, BUNDLE_REPORT_FILE, BUNDLE_COMMAND_OUTCOMES_FILE):
        text = (result.bundleDirectory / name).read_text(encoding="utf-8")
        assert root not in text
        assert "/tmp" not in text
        assert "\\" not in text.replace("\\/", "")
