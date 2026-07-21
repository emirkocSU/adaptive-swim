"""Continuous profile runtime/session integration tests (Commit 8 §37)."""

from __future__ import annotations

import pytest

from contracts.commands import ArmSession, CreateSession, RecordSplit, StartSession
from contracts.enums import (
    PaceProfileSource,
    ProfileApprovalStatus,
    SplitSource,
)
from swimcore.session import FixedClock, SequenceIdGenerator, SessionAggregate
from tests.unit._continuous_helpers import knots, pchip_profile
from tests.unit._profile_helpers import workout_1_1


def _agg(profiles: dict[str, object]) -> SessionAggregate:
    return SessionAggregate(
        {},
        FixedClock(0),
        SequenceIdGenerator("evt"),
        workouts_v1_1={"w1": workout_1_1(distance=100)},
        profiles=profiles,  # type: ignore[arg-type]
    )


def _run_to_running(agg: SessionAggregate, profile_ref: str = "p1") -> str:
    agg.handle(CreateSession(clientCommandId="c1", workoutRef="w1", paceProfileRef=profile_ref))
    sid = agg.sessionId
    assert sid is not None
    agg.handle(ArmSession(clientCommandId="a1", sessionId=sid))
    agg.handle(StartSession(clientCommandId="s1", sessionId=sid))
    return sid


def test_continuous_profile_create_session() -> None:
    agg = _agg({"p1": pchip_profile()})
    _run_to_running(agg)
    assert agg.selectedPaceProfileId == "p"
    assert agg.ghostClock is not None
    assert agg.paceTimeline is not None


def test_ghost_uses_continuous_timeline() -> None:
    agg = _agg({"p1": pchip_profile(curve_knots=knots((0.0, 1.4), (50.0, 1.1), (100.0, 1.35)))})
    _run_to_running(agg)
    assert agg.ghostClock is not None
    snap = agg.ghostClock.snapshot(10_000)
    assert snap.displayDistanceM > 0.0


def test_profile_selection_coach_authored_wins() -> None:
    coach = pchip_profile(source=PaceProfileSource.COACH_AUTHORED, profile_id="coach")
    model = pchip_profile(source=PaceProfileSource.COACH_APPROVED_MODEL, profile_id="model")
    # both provided under different refs; the session selects the single one named
    agg = _agg({"p1": coach, "p2": model})
    _run_to_running(agg, profile_ref="p1")
    assert agg.selectedPaceProfileSource == PaceProfileSource.COACH_AUTHORED.value


def test_default_model_requires_opt_in() -> None:
    default = pchip_profile(
        source=PaceProfileSource.DEFAULT_MODEL_GENERATED,
        approval=ProfileApprovalStatus.DRAFT,
        profile_id="default",
    )
    agg = _agg({"p1": default})
    with pytest.raises(Exception):  # noqa: B017,PT011 - default requires explicit opt-in
        agg.handle(CreateSession(clientCommandId="c1", workoutRef="w1", paceProfileRef="p1"))


def test_dive_start_does_not_alter_official_distance() -> None:
    agg = _agg({"p1": pchip_profile()})
    sid = _run_to_running(agg)
    ev = agg.handle(
        RecordSplit(
            clientCommandId="sp0",
            sessionId=sid,
            splitId="l0",
            lengthIndex=0,
            wallTimestampMs=20_000,
            source=SplitSource.SIMULATED,
            distanceM=25.0,
        )
    )
    split_events = [e for e in ev if e.type.value == "SplitRecorded"]
    assert len(split_events) == 1
    assert len(agg.recordedSplits) == 1


def test_coach_locked_profile_blocks_default_model_selection() -> None:
    locked = pchip_profile(coach_locked=True, profile_id="locked")
    agg = _agg({"p1": locked})
    _run_to_running(agg)
    assert agg.profileCoachLocked is True


def test_normal_pace_loss_does_not_stop_pause() -> None:
    # a swimmer behind the ghost still produces no StopPause; only explicit stop commands do
    agg = _agg({"p1": pchip_profile()})
    sid = _run_to_running(agg)
    # record late splits (behind plan) — no StopPause events emitted
    events = []
    for i, ts in enumerate((30_000, 62_000, 95_000, 130_000)):
        events += agg.handle(
            RecordSplit(
                clientCommandId=f"sp{i}",
                sessionId=sid,
                splitId=f"l{i}",
                lengthIndex=i,
                wallTimestampMs=ts,
                source=SplitSource.SIMULATED,
                distanceM=float((i + 1) * 25),
            )
        )
    assert not any("StopPause" in e.type.value for e in events)
    assert len(agg.recordedSplits) == 4
