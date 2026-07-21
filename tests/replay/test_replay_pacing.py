"""Replay pacing/coach-reset/profile-metadata tests (Commit 7 §16, §20; ADR-021/034)."""

from __future__ import annotations

import pytest

from swimcore.replay import ReplayTransitionError, replay_session
from tests.replay._stream_helpers import StreamBuilder

pytestmark = pytest.mark.replay


def test_coach_reset_reconstruction_opens_and_closes_pending() -> None:
    b = StreamBuilder().running(0).split(0, 20_000).reset_requested(21_000)
    mid = replay_session(b.events).state
    assert mid.pendingCoachPacingReset is not None
    assert mid.pendingCoachPacingReset.reason == "regroup"
    b.reset_applied(40_000).split(1, 40_000)
    done = replay_session(b.events).state
    assert done.pendingCoachPacingReset is None


def test_coach_reset_is_not_a_stop_pause_and_deletes_no_splits() -> None:
    b = StreamBuilder().running(0).split(0, 20_000)
    b.reset_requested(21_000).reset_applied(40_000).split(1, 40_000).completed(40_000)
    state = replay_session(b.events).state
    assert state.stoppedDurationMs == 0  # reset changes NO stopped duration
    assert state.completedStopPauses == () and state.openStopPause is None
    assert state.officialCompletedLengthCount == 2  # old splits preserved
    assert state.wallDurationMs == state.activeDurationMs == 40_000


def test_reset_applied_without_pending_rejected() -> None:
    b = StreamBuilder().running(0).reset_applied(10_000)
    with pytest.raises(ReplayTransitionError, match="without a pending"):
        replay_session(b.events)


def test_conflicting_second_reset_request_rejected() -> None:
    b = StreamBuilder().running(0).reset_requested(10_000, "regroup")
    b.reset_requested(11_000, "different reason")
    with pytest.raises(ReplayTransitionError, match="different coach pacing reset"):
        replay_session(b.events)


def test_pace_target_reconstruction() -> None:
    b = StreamBuilder().running(0).split(0, 20_000)
    b.decision(20_500).pace_changed(20_500, 82.0)
    state = replay_session(b.events).state
    assert state.appliedPaceSecPer100M == 82.0


def test_last_pace_target_wins() -> None:
    b = StreamBuilder().running(0)
    b.pace_changed(10_000, 82.0)
    b.pace_changed(20_000, 84.0)
    assert replay_session(b.events).state.appliedPaceSecPer100M == 84.0


def test_control_decision_reason_preservation() -> None:
    b = StreamBuilder().running(0).decision(10_000)
    decision = replay_session(b.events).state.lastControlDecision
    assert decision is not None
    assert decision.decision == "APPLY"
    assert decision.reasonCodes == ("APPLIED_WITHIN_BOUNDS",)
    assert decision.reasonCode == "APPLIED"
    assert decision.requestSource == "COACH_MANUAL"
    assert decision.suggestedPaceSecPer100M == 82.0
    assert decision.abstained is False and decision.bounded is False


def test_profile_metadata_preserved_from_session_created() -> None:
    b = StreamBuilder()
    b.created(
        0,
        defaultStartMode="DIVE_START",
        selectedPaceProfileId="profile-1",
        selectedPaceProfileVersion="3",
        selectedPaceProfileSource="COACH_AUTHORED",
        selectedPaceProfileType="NEGATIVE_SPLIT",
        profileCoachLocked=True,
        workoutGoal="RACE_SIMULATION",
    )
    state = replay_session(b.events).state
    assert state.workoutRef == "w1"
    assert state.workoutSchemaVersion == "1.0"
    assert state.poolLengthM == 25
    assert state.defaultStartMode == "DIVE_START"
    assert state.selectedPaceProfileId == "profile-1"
    assert state.selectedPaceProfileVersion == "3"
    assert state.selectedPaceProfileSource == "COACH_AUTHORED"
    assert state.selectedPaceProfileType == "NEGATIVE_SPLIT"
    assert state.profileCoachLocked is True
    assert state.workoutGoal == "RACE_SIMULATION"
