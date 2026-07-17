"""Commit 5 — GhostClock wall reconciliation (mid-pool alignment → safe wall anchor)."""

from __future__ import annotations

import pytest

from contracts.workout import WorkoutTemplateVersion
from swimcore.ghost import GhostClock, InvalidWallReconciliationError
from swimcore.pacing import compile_pace_timeline
from swimcore.time import ActiveClock


def _ghost(pool: int) -> GhostClock:
    dist = 100 if pool == 25 else 200
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
                    "distanceM": dist,
                    "rest": {"type": "none"},
                    "segments": [
                        {"fromM": 0, "toM": dist, "mode": "even_pace", "targetPaceSecPer100M": 80.0}
                    ],
                }
            ],
        }
    )
    ac = ActiveClock()
    ac.start(0)
    return GhostClock(compile_pace_timeline(w), ac, pool)


def _paused_then_resumed(pool: int, tracked: float) -> GhostClock:
    g = _ghost(pool)
    g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=tracked)
    g.resume_from_stop_pause(20_000)
    return g


def test_reconcile_at_valid_25m_wall() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    snap = g.reconcile_at_wall(50.0, 20_000)
    assert snap.displayDistanceM == pytest.approx(50.0)
    assert snap.alignmentActive is False


def test_reconcile_at_valid_50m_wall() -> None:
    g = _paused_then_resumed(50, tracked=95.0)
    snap = g.reconcile_at_wall(100.0, 20_000)
    assert snap.displayDistanceM == pytest.approx(100.0)
    assert snap.alignmentActive is False


def test_non_wall_distance_rejected() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(60.0, 20_000)


def test_wall_beyond_total_distance_rejected() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(5000.0, 20_000)


def test_reconciliation_does_not_modify_timeline() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    before = g.snapshot(20_000).timelineDistanceM
    g.reconcile_at_wall(50.0, 20_000)
    after = g.snapshot(20_000).timelineDistanceM
    assert after == pytest.approx(before)  # plan timeline is untouched


def test_reconciliation_clears_temporary_alignment_state() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    assert g.snapshot(20_000).alignmentActive is True
    g.reconcile_at_wall(50.0, 20_000)
    assert g.snapshot(20_000).alignmentActive is False


def test_reconciliation_cannot_move_backward() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    # current display ~48; reconciling to 25 m wall would move backward
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(25.0, 20_000)


# --------------------------------------------------------------------------- C8 additions
from swimcore.pacing import InvalidPoolLengthError  # noqa: E402
from swimcore.time import InvalidClockTimeError  # noqa: E402


def test_reconcile_without_pending_alignment_is_rejected() -> None:
    g = _ghost(25)  # normal ACTIVE ghost, no StopPause
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(50.0, 10_000)


def test_reconcile_only_accepts_next_valid_wall() -> None:
    # pool 25, alignment 48 → expected 50; 75 and 100 rejected
    g = _paused_then_resumed(25, tracked=48.0)
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(75.0, 20_000)
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(100.0, 20_000)
    snap = g.reconcile_at_wall(50.0, 20_000)
    assert snap.displayDistanceM == pytest.approx(50.0)


def test_reconcile_cannot_skip_multiple_walls() -> None:
    g = _paused_then_resumed(25, tracked=48.0)  # expected 50
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(75.0, 20_000)  # skips the 50 m wall


def test_second_reconciliation_is_rejected() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    g.reconcile_at_wall(50.0, 20_000)
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(50.0, 20_000)


def test_new_stop_pause_allows_new_reconciliation() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    g.reconcile_at_wall(50.0, 20_000)
    g.apply_stop_pause(60_000, 65_000, tracked_alignment_distance_m=123.0)
    g.resume_from_stop_pause(65_000)
    snap = g.reconcile_at_wall(125.0, 65_000)  # next wall after 123 in a 25 m pool
    assert snap.displayDistanceM == pytest.approx(125.0)


def test_invalid_pool_length_is_rejected() -> None:
    from contracts.workout import WorkoutTemplateVersion
    from swimcore.pacing import compile_pace_timeline
    from swimcore.time import ActiveClock

    tl = compile_pace_timeline(
        WorkoutTemplateVersion.model_validate(
            {
                "schemaVersion": "1.0",
                "name": "g",
                "poolLengthM": 25,
                "stroke": "freestyle",
                "blocks": [
                    {
                        "type": "repeat",
                        "repetitions": 1,
                        "distanceM": 100,
                        "rest": {"type": "none"},
                        "segments": [
                            {
                                "fromM": 0,
                                "toM": 100,
                                "mode": "even_pace",
                                "targetPaceSecPer100M": 80.0,
                            }
                        ],
                    }
                ],
            }
        )
    )
    ac = ActiveClock()
    ac.start(0)
    for bad in (0, -25):
        with pytest.raises(InvalidPoolLengthError):
            GhostClock(tl, ac, bad)


def test_ghost_snapshot_rejects_historical_time() -> None:
    g = _paused_then_resumed(25, tracked=48.0)  # lastTransition = 20_000
    with pytest.raises(InvalidClockTimeError):
        g.snapshot(5_000)


def test_alignment_sets_expected_next_wall() -> None:
    g = _ghost(25)
    snap = g.apply_stop_pause(10_000, 20_000, tracked_alignment_distance_m=48.0)
    assert snap.expectedReconciliationWallM == pytest.approx(50.0)
    assert snap.wallReconciliationPending is True


def test_reconciliation_clears_pending_alignment() -> None:
    g = _paused_then_resumed(25, tracked=48.0)
    assert g.snapshot(20_000).wallReconciliationPending is True
    snap = g.reconcile_at_wall(50.0, 20_000)
    assert snap.wallReconciliationPending is False
    assert snap.expectedReconciliationWallM is None
    assert snap.alignmentActive is False


def test_normal_active_ghost_cannot_be_repositioned_at_wall() -> None:
    # Without a confirmed StopPause the ghost has no pending alignment → cannot be moved.
    g = _ghost(25)
    with pytest.raises(InvalidWallReconciliationError):
        g.reconcile_at_wall(50.0, 30_000)


def test_constructor_rejects_non_wall_total_distance() -> None:
    from contracts.workout import WorkoutTemplateVersion
    from swimcore.pacing import compile_pace_timeline
    from swimcore.time import ActiveClock

    # total 100 m is not a multiple of a 30 m pool → not a wall boundary
    tl = compile_pace_timeline(
        WorkoutTemplateVersion.model_validate(
            {
                "schemaVersion": "1.0",
                "name": "g",
                "poolLengthM": 25,
                "stroke": "freestyle",
                "blocks": [
                    {
                        "type": "repeat",
                        "repetitions": 1,
                        "distanceM": 100,
                        "rest": {"type": "none"},
                        "segments": [
                            {
                                "fromM": 0,
                                "toM": 100,
                                "mode": "even_pace",
                                "targetPaceSecPer100M": 80.0,
                            }
                        ],
                    }
                ],
            }
        )
    )
    ac = ActiveClock()
    ac.start(0)
    with pytest.raises(InvalidPoolLengthError):
        GhostClock(tl, ac, 30)
