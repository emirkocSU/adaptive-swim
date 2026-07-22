"""Failure behaviour of the Phase 1 slice (ADR-041 §16).

A failed command never persists events, a duplicate retry never changes the journal, and
a corrupt or contradictory input is rejected rather than silently normalised.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from e2e.cases import CASE_BY_ID
from e2e.errors import E2ECaseError
from e2e.runner import run_phase1_vertical_slice
from e2e.types import Phase1E2EResult
from persistence.errors import EventLogError
from persistence.jsonl_event_log import JsonlSessionEventLog


def test_a_rejected_command_appends_nothing(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case("complete-while-stop-paused")
    rejected = [o for o in result.commandOutcomes if o.outcome == "REJECTED"]
    assert rejected and all(o.eventCount == 0 for o in rejected)
    persisted = {
        json.loads(line)["clientCommandId"]
        for line in result.journalPath.read_bytes().split(b"\n")
        if line.strip()
    }
    for outcome in rejected:
        assert outcome.clientCommandId not in persisted
    flattened = [seq for batch in result.eventBatches for seq in batch]
    assert flattened == list(range(1, len(flattened) + 1))


def test_a_duplicate_retry_leaves_the_journal_unchanged(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case("duplicate-command-durability")
    replays = [o for o in result.commandOutcomes if o.outcome == "IDEMPOTENT_REPLAY"]
    assert len(replays) == 1
    assert replays[0].eventCount == 0
    lines = [line for line in result.journalPath.read_bytes().split(b"\n") if line.strip()]
    client_ids = [json.loads(line)["clientCommandId"] for line in lines]
    assert len(set(client_ids)) == len(client_ids)
    assert len(lines) == result.verificationManifest.batchCount


def test_no_partial_report_is_produced_for_an_invalid_case() -> None:
    case = CASE_BY_ID["normal-continuous-completion"]()
    with pytest.raises(E2ECaseError):
        type(case)(
            caseId=case.caseId,
            caseVersion=case.caseVersion,
            seed=case.seed,
            workout=case.workout,
            paceProfiles=case.paceProfiles,
            selectedProfileId="not-a-profile",
            scenario=case.scenario,
        )


def test_corrupt_middle_journal_is_rejected(
    run_case: Callable[..., Phase1E2EResult], tmp_path: Path
) -> None:
    result = run_case("normal-continuous-completion")
    lines = [line for line in result.journalPath.read_bytes().split(b"\n") if line.strip()]
    corrupted = tmp_path / "corrupt.jsonl"
    damaged = list(lines)
    damaged[2] = damaged[2][: len(damaged[2]) // 2]
    corrupted.write_bytes(b"\n".join(damaged) + b"\n")
    with pytest.raises(EventLogError):
        JsonlSessionEventLog(corrupted, result.replayFinalState.sessionId).read_all()


def test_the_runner_never_touches_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def deny(*args: object, **kwargs: object) -> None:
        raise AssertionError("the Phase 1 e2e runner must never open a socket")

    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    result = run_phase1_vertical_slice(
        case=CASE_BY_ID["stop-during-planned-rest"](),
        output_directory=Path(__import__("tempfile").mkdtemp()) / "no-network",
    )
    assert result.allChecksPassed


def test_missing_observations_never_fabricate_curve_metrics(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    curve = run_case("unreliable-observation-report").sessionReport.continuousCurveAnalysis
    assert curve.available is False
    assert curve.status.value in {"LOW_QUALITY", "INSUFFICIENT_DATA"}
    assert curve.reason is not None
    assert curve.curveDeviationMean is None
    assert curve.curveDeviationByPhase == ()
