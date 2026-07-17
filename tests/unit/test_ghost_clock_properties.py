"""Commit 5 — property-based invariants for the deterministic clocks and ghost."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from contracts.workout import WorkoutTemplateVersion
from swimcore.ghost import GhostClock, GhostState
from swimcore.pacing import compile_pace_timeline
from swimcore.time import ActiveClock, SimClock

_delta = st.integers(min_value=0, max_value=10_000)


@given(deltas=st.lists(_delta, max_size=30))
def test_sim_clock_never_moves_backward(deltas: list[int]) -> None:
    c = SimClock(0)
    prev = c.now_ms()
    for d in deltas:
        c.advance_ms(d)
        assert c.now_ms() >= prev
        prev = c.now_ms()


@given(
    start=st.integers(min_value=0, max_value=5_000),
    now=st.integers(min_value=0, max_value=200_000),
)
def test_active_never_exceeds_wall(start: int, now: int) -> None:
    c = ActiveClock()
    c.start(start)
    if now < start:
        return
    snap = c.snapshot(now)
    assert 0 <= snap.activeElapsedMs <= snap.wallElapsedMs
    assert snap.stoppedElapsedMs == snap.wallElapsedMs - snap.activeElapsedMs


@given(
    stop_start=st.integers(min_value=1_000, max_value=50_000),
    stop_len=st.integers(min_value=0, max_value=30_000),
    tail=st.integers(min_value=0, max_value=30_000),
)
def test_stopped_equals_wall_minus_active(stop_start: int, stop_len: int, tail: int) -> None:
    c = ActiveClock()
    c.start(0)
    confirmed = stop_start + stop_len
    c.freeze_from(stop_start, confirmed)
    c.resume(confirmed)
    now = confirmed + tail
    snap = c.snapshot(now)
    assert snap.stoppedElapsedMs == stop_len
    assert snap.activeElapsedMs == snap.wallElapsedMs - stop_len


def _ghost() -> GhostClock:
    w = WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "g",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 10,
                    "distanceM": 100,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": 100, "mode": "even_pace", "targetPaceSecPer100M": 80.0}
                    ],
                }
            ],
        }
    )
    ac = ActiveClock()
    ac.start(0)
    return GhostClock(compile_pace_timeline(w), ac, 25)


@given(times=st.lists(st.integers(min_value=0, max_value=800_000), min_size=1, max_size=15))
def test_ghost_display_monotonic_and_bounded_while_active(times: list[int]) -> None:
    g = _ghost()
    prev = 0.0
    for t in sorted(times):
        s = g.snapshot(t)
        assert 0.0 <= s.displayDistanceM <= 1000.0 + 1e-6
        assert s.displayDistanceM >= prev - 1e-6
        prev = s.displayDistanceM


@given(pause_query=st.integers(min_value=20_000, max_value=200_000))
def test_ghost_display_constant_while_paused(pause_query: int) -> None:
    g = _ghost()
    g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=13.0)
    assert g.snapshot(pause_query).displayDistanceM == 13.0
    assert g.snapshot(pause_query).state is GhostState.STOP_PAUSED


@given(t=st.integers(min_value=0, max_value=800_000))
def test_same_inputs_produce_identical_snapshots(t: int) -> None:
    g1 = _ghost()
    g2 = _ghost()
    assert g1.snapshot(t) == g2.snapshot(t)


@given(t=st.integers(min_value=6_000, max_value=400_000))
def test_timeline_distance_independent_of_alignment_offset(t: int) -> None:
    from swimcore.pacing import ghost_distance_at_active_time

    aligned = _ghost()
    aligned.apply_stop_pause(5_000, 6_000, tracked_alignment_distance_m=50.0)
    aligned.resume_from_stop_pause(6_000)
    snap = aligned.snapshot(t)
    # timeline position is the pure function of ACTIVE time, unaffected by the display offset
    expected = ghost_distance_at_active_time(
        aligned._timeline, snap.activeElapsedMs / 1000.0, clamp=True
    ).distanceM
    assert snap.timelineDistanceM == expected


@given(
    stop_start=st.integers(min_value=1_000, max_value=40_000),
    stop_len=st.integers(min_value=0, max_value=20_000),
    resume_extra=st.integers(min_value=0, max_value=10_000),
    tail=st.integers(min_value=0, max_value=20_000),
)
def test_active_clock_invariants_hold_after_transitions(
    stop_start: int, stop_len: int, resume_extra: int, tail: int
) -> None:
    c = ActiveClock()
    c.start(0)
    confirmed = stop_start + stop_len
    c.freeze_from(stop_start, confirmed)
    resumed = confirmed + resume_extra
    c.resume(resumed)
    now = resumed + tail
    snap = c.snapshot(now)
    assert 0 <= snap.activeElapsedMs <= snap.wallElapsedMs
    assert 0 <= snap.stoppedElapsedMs <= snap.wallElapsedMs
    assert snap.wallElapsedMs == snap.activeElapsedMs + snap.stoppedElapsedMs
    assert now >= snap.lastTransitionAtMs  # transition times remain monotonic


@given(deltas=st.lists(st.integers(min_value=0, max_value=20_000), min_size=1, max_size=12))
def test_active_elapsed_never_decreases(deltas: list[int]) -> None:
    c = ActiveClock()
    c.start(0)
    now = 0
    prev = 0
    for d in deltas:
        now += d
        active = c.active_elapsed_ms(now)
        assert active >= prev
        prev = active
