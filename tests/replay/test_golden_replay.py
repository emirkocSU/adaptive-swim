"""Golden replay journals: determinism + expected historical state (Commit 7 §19, §26)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from persistence.jsonl_event_log import JsonlSessionEventLog
from swimcore.replay import replay_session
from swimcore.session.state import SessionState
from tests.replay._golden_helpers import (
    GOLDEN_NAMES,
    write_golden_journal,
)

pytestmark = pytest.mark.replay

GOLDEN_DIR = Path(__file__).parent / "goldens"


def _session_id_of(path: Path) -> str:
    import json

    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    session_id: str = first["sessionId"]
    return session_id


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_committed_golden_matches_regenerated(name: str, tmp_path: Path) -> None:
    committed = GOLDEN_DIR / f"{name}.jsonl"
    regenerated = write_golden_journal(name, tmp_path)
    assert regenerated.read_bytes() == committed.read_bytes(), (
        f"golden {name} drifted from the deterministic command sequence"
    )


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_same_history_in_two_directories_is_byte_identical(name: str, tmp_path: Path) -> None:
    """§26: sha256(logA) == sha256(logB) for the same deterministic history."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    path_a = write_golden_journal(name, dir_a)
    path_b = write_golden_journal(name, dir_b)
    sha_a = hashlib.sha256(path_a.read_bytes()).hexdigest()
    sha_b = hashlib.sha256(path_b.read_bytes()).hexdigest()
    assert sha_a == sha_b


def _replay_golden(name: str):  # noqa: ANN202 - test helper
    path = GOLDEN_DIR / f"{name}.jsonl"
    log = JsonlSessionEventLog(path, _session_id_of(path))
    result = log.read_all()
    assert result.notices == ()
    return replay_session(list(result.events))


def test_normal_session_golden_state() -> None:
    state = _replay_golden("normal-session").state
    assert state.sessionId == "session-create-001"
    assert state.lifecycleState is SessionState.COMPLETED
    assert state.stoppedDurationMs == 0
    assert state.lifecyclePausedDurationMs == 0
    assert state.wallDurationMs == state.elapsedDurationMs == state.activeDurationMs == 80_000
    assert state.officialCompletedLengthCount == 4
    assert state.officialCompletedDistanceM == 100.0
    assert state.poolLengthM == 25 and state.workoutSchemaVersion == "1.0"
    assert state.workoutRef == "w1"  # profile metadata carried through


def test_stop_pause_session_golden_state() -> None:
    state = _replay_golden("stop-pause-session").state
    assert state.lifecycleState is SessionState.COMPLETED
    assert state.wallDurationMs == 110_000
    assert state.stoppedDurationMs == 25_000
    assert state.activeDurationMs == 85_000
    assert state.elapsedDurationMs == 110_000
    assert state.activeDurationMs + state.stoppedDurationMs == state.elapsedDurationMs
    assert len(state.completedStopPauses) == 1
    interval = state.completedStopPauses[0]
    assert (interval.startedAtMs, interval.endedAtMs, interval.durationMs) == (
        25_000,
        50_000,
        25_000,
    )
    assert interval.trigger == "MANUAL_INCIDENT"
    assert state.wallReconciliationPending is False  # closed by the wall-50 split
    assert state.officialCompletedLengthCount == 4


def test_coach_reset_session_golden_state() -> None:
    state = _replay_golden("coach-reset-session").state
    assert state.lifecycleState is SessionState.COMPLETED
    assert state.stoppedDurationMs == 0  # reset is NOT a StopPause
    assert state.completedStopPauses == ()
    assert state.pendingCoachPacingReset is None  # pending closed by Applied
    assert state.officialCompletedLengthCount == 4  # old splits preserved
    assert state.appliedPaceSecPer100M == 82.0
    decision = state.lastControlDecision
    assert decision is not None
    assert decision.decision == "APPLY"
    assert decision.reasonCodes == ("APPLIED_WITHIN_BOUNDS",)


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_golden_journals_have_one_line_per_command(name: str) -> None:
    path = GOLDEN_DIR / f"{name}.jsonl"
    log = JsonlSessionEventLog(path, _session_id_of(path))
    result = log.read_all()
    cids = [b.clientCommandId for b in result.batches]
    assert len(cids) == len(set(cids))
    assert path.read_bytes().count(b"\n") == len(result.batches)
