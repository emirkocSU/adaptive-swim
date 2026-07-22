from __future__ import annotations

from analytics.stops import build_stop_pause_analysis
from swimcore.replay.reducer import replay_session
from tests.replay._stream_helpers import StreamBuilder


def test_stop_pause_summary_uses_retroactive_start() -> None:
    builder = (
        StreamBuilder()
        .running(0)
        .split(0, 20_000)
        .stop_started(started_at=25_000, confirmed_at=30_000)
        .stop_resolved(started_at=25_000, ended_at=35_000)
        .split(1, 50_000)
        .completed(50_000)
    )
    state = replay_session(builder.events).state
    summary = build_stop_pause_analysis(state, builder.events)
    assert summary.stopPauseCount == 1
    assert summary.totalStoppedDurationMs == 10_000
    assert summary.intervals[0].retroactiveFreezeMs == 5_000
