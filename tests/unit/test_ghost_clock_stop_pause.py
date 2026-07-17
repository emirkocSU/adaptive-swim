"""Commit 5 — GhostClock StopPause: retroactive freeze + controlled alignment."""

from __future__ import annotations

import pytest

from contracts.workout import WorkoutTemplateVersion
from swimcore.ghost import (
    GhostClock,
    GhostState,
    InvalidAlignmentDistanceError,
    InvalidGhostTransitionError,
)
from swimcore.pacing import compile_pace_timeline
from swimcore.time import ActiveClock


def _ghost(pool: int = 25) -> GhostClock:
    w = WorkoutTemplateVersion.model_validate(
        {
            "schemaVersion": "1.0",
            "name": "g",
            "poolLengthM": pool,
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
    return GhostClock(compile_pace_timeline(w), ac, pool)


def test_ghost_freezes_retroactively_at_stop_start() -> None:
    g = _ghost()
    snap = g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=12.5)
    assert snap.activeElapsedMs == 10_000  # frozen at the real stop start
    assert snap.stoppedElapsedMs == 10_000
    assert snap.state is GhostState.STOP_PAUSED


def test_ghost_aligns_to_supplied_tracked_point() -> None:
    g = _ghost()
    snap = g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=13.0)
    assert snap.displayDistanceM == pytest.approx(13.0)
    assert snap.alignmentActive is True


def test_ghost_remains_fixed_during_pause() -> None:
    g = _ghost()
    g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=13.0)
    for t in (20_000, 25_000, 40_000):
        s = g.snapshot(t)
        assert s.displayDistanceM == pytest.approx(13.0)
        assert s.activeElapsedMs == 10_000


def test_resume_starts_from_aligned_display_position() -> None:
    g = _ghost()
    g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=13.0)
    r = g.resume_from_stop_pause(20_000)
    assert r.displayDistanceM == pytest.approx(13.0)
    assert r.state is GhostState.ACTIVE
    # a little later, display advances from 13.0 by the plan increment (no jump back)
    later = g.snapshot(28_000)  # active 18 s → timeline 22.5 m; anchor timeline 12.5 m
    assert later.displayDistanceM == pytest.approx(13.0 + (22.5 - 12.5))


def test_timeline_context_and_target_pace_unchanged() -> None:
    g = _ghost()
    before = g.snapshot(10_000).targetPaceSecPer100M
    g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=13.0)
    g.resume_from_stop_pause(20_000)
    after = g.snapshot(20_000).targetPaceSecPer100M
    assert after == pytest.approx(before)  # same pace curve context


def test_no_jump_back_to_old_planned_position() -> None:
    g = _ghost()
    g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=40.0)
    r = g.resume_from_stop_pause(20_000)
    # ghost stays at aligned 40 m, never snaps back to plan's 12.5 m
    assert r.displayDistanceM == pytest.approx(40.0)
    assert g.snapshot(21_000).displayDistanceM >= 40.0


def test_multiple_stop_pause_intervals() -> None:
    g = _ghost()
    g.apply_stop_pause(10_000, 15_000, tracked_alignment_distance_m=13.0)
    g.resume_from_stop_pause(15_000)
    # a pending alignment must be reconciled before the next StopPause
    g.reconcile_at_wall(25.0, 15_000)
    s2 = g.apply_stop_pause(25_000, 30_000, tracked_alignment_distance_m=48.0)
    assert s2.state is GhostState.STOP_PAUSED
    assert s2.displayDistanceM == pytest.approx(48.0)


def test_alignment_at_zero_metres() -> None:
    g = _ghost()
    snap = g.apply_stop_pause(1_000, 12_000, tracked_alignment_distance_m=0.0)
    assert snap.displayDistanceM == 0.0


def test_alignment_near_final_distance() -> None:
    g = _ghost()
    snap = g.apply_stop_pause(1_000, 12_000, tracked_alignment_distance_m=1000.0)
    assert snap.displayDistanceM == pytest.approx(1000.0)


def test_alignment_below_zero_rejected() -> None:
    g = _ghost()
    with pytest.raises(InvalidAlignmentDistanceError):
        g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=-1.0)


def test_alignment_above_total_rejected() -> None:
    g = _ghost()
    with pytest.raises(InvalidAlignmentDistanceError):
        g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=5000.0)


def test_alignment_nan_infinity_rejected() -> None:
    g = _ghost()
    for bad in (float("nan"), float("inf")):
        with pytest.raises(InvalidAlignmentDistanceError):
            g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=bad)


def test_cannot_resume_when_active() -> None:
    g = _ghost()
    with pytest.raises(InvalidGhostTransitionError):
        g.resume_from_stop_pause(1_000)


def test_cannot_stop_pause_when_already_paused() -> None:
    g = _ghost()
    g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=13.0)
    with pytest.raises(InvalidGhostTransitionError):
        g.apply_stop_pause(21_000, 22_000, tracked_alignment_distance_m=13.0)


# --------------------------------------------------------------------------- forward-only (fix 1)
def test_ghost_stop_pause_cannot_rewind_after_later_snapshot() -> None:
    from swimcore.time import InvalidClockTimeError

    g = _ghost()
    g.snapshot(100_000)  # ghost/clock has observed 100 s
    with pytest.raises(InvalidClockTimeError):
        # a StopPause confirmed at 60 s is in the past → rejected, no rewind
        g.apply_stop_pause(50_000, 60_000, tracked_alignment_distance_m=13.0)
