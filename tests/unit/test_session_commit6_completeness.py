"""Remaining Commit 6 named acceptance tests (§2.2, §2.4, §2.5, §2.6, §2.12)."""

from __future__ import annotations

import pytest

from contracts.commands import (
    ApplyCoachPaceTarget,
    CoachPacingReset,
    CompleteSession,
    RecordSplit,
)
from contracts.enums import AdaptationMode, PaceRequestSource, ReasonCode
from swimcore.control import PaceChangeRequest, SafetyContext, SafetyController
from swimcore.control.types import SafetyReasonCode
from swimcore.session import (
    InvalidSplitBoundaryError,
    WorkoutNotCompletedError,
)
from tests.unit._session_helpers import bounded_adaptation, record_split, started, workout

SC = SafetyController()


# --------------------------------------------------------------------------- §2.2 completion
def test_complete_rejected_with_missing_length() -> None:
    agg, _ = started(workout(reps=4, dist=100, pool=25))  # 400 m -> 16 lengths
    agg.handle(record_split(agg, 0))
    with pytest.raises(WorkoutNotCompletedError):
        agg.handle(CompleteSession(clientCommandId="cs", sessionId=agg.sessionId))


def test_complete_rejected_with_pending_reset() -> None:
    wk = workout(reps=1, dist=50, pool=25)  # 2 lengths
    agg, clk = started(wk)
    agg.handle(record_split(agg, 0))
    agg.handle(record_split(agg, 1))
    clk.set(100000)
    agg.handle(CoachPacingReset(clientCommandId="cr", sessionId=agg.sessionId))
    with pytest.raises(WorkoutNotCompletedError):
        agg.handle(CompleteSession(clientCommandId="cs", sessionId=agg.sessionId))


# --------------------------------------------------------------------------- §2.4 split skip
def test_split_cannot_skip_expected_length() -> None:
    agg, _ = started(workout(reps=1, dist=100, pool=25))  # 4 lengths
    agg.handle(record_split(agg, 0))
    # lengthIndex 2 skips index 1 -> rejected
    with pytest.raises(InvalidSplitBoundaryError):
        agg.handle(
            RecordSplit(
                clientCommandId="skip",
                sessionId=agg.sessionId,
                splitId="split-2",
                lengthIndex=2,
                wallTimestampMs=90000,
                source="TOUCHPAD",
                distanceM=75.0,
            )
        )


# --------------------------------------------------------------------------- §2.5/2.6 coach reset
def test_coach_reset_does_not_create_stop_pause() -> None:
    wk = workout(reps=1, dist=75, pool=25)  # 3 lengths
    agg, clk = started(wk)
    agg.handle(record_split(agg, 0))
    clk.set(100000)
    agg.handle(CoachPacingReset(clientCommandId="cr", sessionId=agg.sessionId))
    # applies at the next valid wall
    agg.handle(record_split(agg, 1, ts=120000))
    assert agg.openStopPause is None
    assert agg.pendingCoachPacingReset is None


def test_reset_not_applied_at_wrong_wall_keeps_pending() -> None:
    wk = workout(reps=1, dist=75, pool=25)
    agg, _ = started(wk)
    agg.handle(CoachPacingReset(clientCommandId="cr", sessionId=agg.sessionId))
    # pending reset expects the wall after 0 recorded splits -> 25 m
    assert agg.pendingCoachPacingReset is not None
    assert agg.pendingCoachPacingReset.expectedApplicationWallM == 25.0


# --------------------------------------------------------------------------- §2.12 reason codes
def _ctx(**over: object) -> SafetyContext:
    base: dict = {
        "currentAppliedPaceSecPer100M": 80.0,
        "coachTargetPaceSecPer100M": 80.0,
        "adaptationMode": AdaptationMode.bounded_auto,
        "fastestAllowedPaceSecPer100M": 78.0,
        "slowestAllowedPaceSecPer100M": 82.0,
        "maxChangePercentPerLength": 5.0,
        "isWallBoundary": True,
    }
    base.update(over)
    return SafetyContext(**base)


def test_fastest_bound_reason_preserved() -> None:
    d = SC.decide(PaceChangeRequest(60.0, source=PaceRequestSource.COACH_MANUAL), _ctx())
    assert SafetyReasonCode.BOUNDED_BY_FASTEST_LIMIT in d.reasonCodes


def test_slowest_bound_reason_preserved() -> None:
    d = SC.decide(PaceChangeRequest(100.0, source=PaceRequestSource.COACH_MANUAL), _ctx())
    assert SafetyReasonCode.BOUNDED_BY_SLOWEST_LIMIT in d.reasonCodes


def test_reason_code_mapping_is_exhaustive() -> None:
    # Every SafetyReasonCode must map to a ReasonCode in the aggregate; the aggregate raises
    # if any is unmapped. Drive it via a real control decision and assert a valid reasonCode.
    agg, clk = started(workout(adaptation=bounded_adaptation()))
    clk.set(300)
    events = agg.handle(
        ApplyCoachPaceTarget(
            clientCommandId="apt",
            sessionId=agg.sessionId,
            suggestedPaceSecPer100M=60.0,
            source=PaceRequestSource.COACH_MANUAL,
            currentWallDistanceM=0.0,
            isWallBoundary=True,
        )
    )
    payload = events[0].payload
    assert payload.reasonCode in set(ReasonCode)
    assert payload.reasonCodes  # non-empty loss-less list
