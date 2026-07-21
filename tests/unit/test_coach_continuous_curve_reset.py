"""Coach continuous-curve reset tests (Commit 8 §20, §37)."""

from __future__ import annotations

import pytest

from contracts.commands import (
    ArmSession,
    CoachPacingReset,
    CreateSession,
    RecordSplit,
    StartSession,
)
from contracts.enums import SplitSource
from swimcore.session import FixedClock, SequenceIdGenerator, SessionAggregate
from tests.unit._continuous_helpers import pchip_profile
from tests.unit._profile_helpers import workout_1_1


def _setup(clock: FixedClock) -> tuple[SessionAggregate, str]:
    p1 = pchip_profile(target_time=80.0, profile_id="p1")
    p2 = pchip_profile(target_time=100.0, profile_id="p2", profile_version="1")
    agg = SessionAggregate(
        {},
        clock,
        SequenceIdGenerator("evt"),
        workouts_v1_1={"w1": workout_1_1(distance=100)},
        profiles={"p1": p1, "pRepl": p2},
    )
    agg.handle(CreateSession(clientCommandId="c1", workoutRef="w1", paceProfileRef="p1"))
    sid = agg.sessionId
    assert sid is not None
    agg.handle(ArmSession(clientCommandId="a1", sessionId=sid))
    agg.handle(StartSession(clientCommandId="s1", sessionId=sid))
    return agg, sid


def _split(agg: SessionAggregate, sid: str, index: int, ts: int) -> list:
    return agg.handle(
        RecordSplit(
            clientCommandId=f"sp{index}",
            sessionId=sid,
            splitId=f"l{index}",
            lengthIndex=index,
            wallTimestampMs=ts,
            source=SplitSource.SIMULATED,
            distanceM=float((index + 1) * 25),
        )
    )


def test_reset_applies_at_next_wall_not_immediately() -> None:
    clock = FixedClock(0)
    agg, sid = _setup(clock)
    _split(agg, sid, 0, 20_000)
    clock.set(21_000)
    ev = agg.handle(
        CoachPacingReset(
            clientCommandId="r1", sessionId=sid, reason="x", replacementPaceProfileRef="pRepl"
        )
    )
    assert [e.type.value for e in ev] == ["CoachPacingResetRequested"]
    assert agg.pendingCoachPacingReset is not None
    assert agg.pendingCoachPacingReset.replacementProfileId == "p2"
    # still on the original profile until the wall
    assert agg.selectedPaceProfileId == "p1"


def test_reset_applied_swaps_profile_at_wall() -> None:
    clock = FixedClock(0)
    agg, sid = _setup(clock)
    _split(agg, sid, 0, 20_000)
    clock.set(21_000)
    agg.handle(
        CoachPacingReset(
            clientCommandId="r1", sessionId=sid, reason="x", replacementPaceProfileRef="pRepl"
        )
    )
    ev = _split(agg, sid, 1, 40_000)
    applied = [e for e in ev if e.type.value == "CoachPacingResetApplied"]
    assert len(applied) == 1
    payload = applied[0].payload
    assert payload.previousPaceProfileId == "p1"
    assert payload.replacementPaceProfileId == "p2"
    assert payload.replacementTargetTotalTimeSec is not None
    assert agg.selectedPaceProfileId == "p2"
    assert agg.pendingCoachPacingReset is None


def test_reset_is_not_stop_pause_and_keeps_splits() -> None:
    clock = FixedClock(0)
    agg, sid = _setup(clock)
    _split(agg, sid, 0, 20_000)
    clock.set(21_000)
    agg.handle(
        CoachPacingReset(
            clientCommandId="r1", sessionId=sid, reason="x", replacementPaceProfileRef="pRepl"
        )
    )
    _split(agg, sid, 1, 40_000)
    assert len(agg.recordedSplits) == 2  # prior split preserved
    assert agg.ghostClock is not None
    snap = agg.ghostClock.snapshot(40_000)
    assert snap.stoppedElapsedMs == 0  # no stopped duration added


def test_reset_without_replacement_keeps_plain_behaviour() -> None:
    clock = FixedClock(0)
    agg, sid = _setup(clock)
    _split(agg, sid, 0, 20_000)
    clock.set(21_000)
    agg.handle(CoachPacingReset(clientCommandId="r1", sessionId=sid, reason="regroup"))
    assert agg.pendingCoachPacingReset is not None
    assert agg.pendingCoachPacingReset.replacementProfileId is None
    ev = _split(agg, sid, 1, 40_000)
    assert any(e.type.value == "CoachPacingResetApplied" for e in ev)
    assert agg.selectedPaceProfileId == "p1"  # unchanged


def test_unknown_replacement_ref_rejected_atomically() -> None:
    clock = FixedClock(0)
    agg, sid = _setup(clock)
    _split(agg, sid, 0, 20_000)
    clock.set(21_000)
    with pytest.raises(Exception):  # noqa: B017,PT011
        agg.handle(
            CoachPacingReset(
                clientCommandId="r1", sessionId=sid, reason="x", replacementPaceProfileRef="nope"
            )
        )
    assert agg.pendingCoachPacingReset is None  # nothing pending after atomic rejection


def test_replacement_pool_mismatch_rejected() -> None:
    clock = FixedClock(0)
    p1 = pchip_profile(profile_id="p1")
    p2_50 = pchip_profile(pool=50, total=100.0, profile_id="p2")
    agg = SessionAggregate(
        {},
        clock,
        SequenceIdGenerator("evt"),
        workouts_v1_1={"w1": workout_1_1(distance=100)},
        profiles={"p1": p1, "pRepl": p2_50},
    )
    agg.handle(CreateSession(clientCommandId="c1", workoutRef="w1", paceProfileRef="p1"))
    sid = agg.sessionId
    assert sid is not None
    agg.handle(ArmSession(clientCommandId="a1", sessionId=sid))
    agg.handle(StartSession(clientCommandId="s1", sessionId=sid))
    _split(agg, sid, 0, 20_000)
    clock.set(21_000)
    with pytest.raises(Exception):  # noqa: B017,PT011
        agg.handle(
            CoachPacingReset(
                clientCommandId="r1", sessionId=sid, reason="x", replacementPaceProfileRef="pRepl"
            )
        )
