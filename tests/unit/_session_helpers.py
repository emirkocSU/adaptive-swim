"""Shared builders for Commit 6 session tests."""

from __future__ import annotations

from contracts.workout import WorkoutTemplateVersion
from swimcore.session import FixedClock, SequenceIdGenerator, SessionAggregate


def workout(adaptation: dict | None = None, reps: int = 10, dist: int = 100, pool: int = 25):
    block: dict = {
        "type": "repeat",
        "repetitions": reps,
        "distanceM": dist,
        "rest": {"type": "none"},
        "segments": [{"fromM": 0, "toM": dist, "mode": "even_pace", "targetPaceSecPer100M": 80.0}],
    }
    if adaptation is not None:
        block["adaptation"] = adaptation
    return WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "wk",
            "poolLengthM": pool,
            "stroke": "freestyle",
            "blocks": [block],
        }
    )


def bounded_adaptation() -> dict:
    return {
        "mode": "bounded_auto",
        "maxChangePercentPerLength": 5.0,
        "fastestAllowedPaceSecPer100M": 76.0,
        "slowestAllowedPaceSecPer100M": 90.0,
    }


def new_aggregate(wk=None, clock_ms: int = 0) -> tuple[SessionAggregate, FixedClock]:
    wk = wk if wk is not None else workout()
    clk = FixedClock(clock_ms)
    agg = SessionAggregate({"w1": wk}, clk, SequenceIdGenerator())
    return agg, clk


def started(wk=None) -> tuple[SessionAggregate, FixedClock]:
    from contracts.commands import ArmSession, CreateSession, StartSession

    agg, clk = new_aggregate(wk)
    agg.handle(CreateSession(clientCommandId="create", workoutRef="w1"))
    clk.set(100)
    agg.handle(ArmSession(clientCommandId="arm", sessionId=agg.sessionId))
    clk.set(200)
    agg.handle(StartSession(clientCommandId="start", sessionId=agg.sessionId))
    return agg, clk


def record_split(
    agg, length_index: int, ts: int | None = None, pool: int = 25, cid: str | None = None
):
    from contracts.commands import RecordSplit

    ts = ts if ts is not None else 40000 * (length_index + 1)
    cid = cid if cid is not None else f"sp{length_index}"
    return RecordSplit(
        clientCommandId=cid,
        sessionId=agg.sessionId,
        splitId=f"split-{length_index}",
        lengthIndex=length_index,
        wallTimestampMs=ts,
        source="TOUCHPAD",
        distanceM=float((length_index + 1) * pool),
    )
