"""GhostClock: drives the Commit-4 pace timeline with the Commit-5 ActiveClock.

The ghost advances along the *active-time* timeline. It does not track the real swimmer or
measure pace loss — on a normal/large pace loss the ghost stays ACTIVE and keeps moving; no
alignment or wall reposition happens. Alignment happens **only** during an externally
confirmed StopPause, using an externally supplied tracked point (never estimated).

Two positions are kept strictly separate:
- ``timelineDistanceM`` — the unchanging mathematical plan position for the current active
  time;
- ``displayDistanceM`` — the shown position after any temporary alignment offset, computed
  from an explicit :class:`GhostAnchor` so the ghost resumes from where the swimmer stopped
  rather than snapping back to the plan.

A temporary mid-pool alignment is reconciled **exactly once**, at the next valid wall after
the tracked point (or at the tracked wall itself when the swimmer is already on a wall). The
next-wall distance is computed with the authoritative Commit-4 wall helper — no second
formula. Reconciliation moves only the ghost display anchor; it does not touch workout
length/set/split state or perform official session accounting (that is Commit 6).
"""

from __future__ import annotations

import math

from swimcore.ghost.errors import (
    InvalidAlignmentDistanceError,
    InvalidGhostTransitionError,
    InvalidWallReconciliationError,
)
from swimcore.ghost.types import GhostAnchor, GhostSnapshot, GhostState
from swimcore.pacing import (
    InvalidPoolLengthError,
    PaceTimeline,
    is_wall_boundary,
    next_wall_boundary,
)
from swimcore.pacing.timeline import ghost_distance_at_active_time
from swimcore.time import ActiveClock

_WALL_TOL = 1e-6


class GhostClock:
    def __init__(
        self,
        timeline: PaceTimeline,
        active_clock: ActiveClock,
        pool_length_m: int,
    ) -> None:
        if not math.isfinite(pool_length_m):
            raise InvalidPoolLengthError(f"pool length must be finite, got {pool_length_m}")
        if pool_length_m <= 0:
            raise InvalidPoolLengthError(f"pool length must be > 0, got {pool_length_m}")
        if not math.isfinite(timeline.totalDistanceM) or timeline.totalDistanceM <= 0.0:
            raise InvalidPoolLengthError(
                f"timeline total distance must be > 0, got {timeline.totalDistanceM}"
            )
        if not is_wall_boundary(timeline.totalDistanceM, pool_length_m):
            raise InvalidPoolLengthError(
                f"timeline total distance {timeline.totalDistanceM} is not a wall boundary "
                f"for pool length {pool_length_m}"
            )
        self._timeline = timeline
        self._clock = active_clock
        self._pool_length_m = pool_length_m
        self._state = GhostState.ACTIVE
        self._alignment_active = False
        self._wall_reconciliation_pending = False
        self._expected_reconciliation_wall_m: float | None = None
        self._anchor = GhostAnchor(
            anchorActiveElapsedSec=0.0,
            anchorTimelineDistanceM=0.0,
            anchorDisplayDistanceM=0.0,
        )

    # ---------------------------------------------------------------- helpers
    def _timeline_distance_at_active(self, active_ms: int) -> tuple[float, float]:
        active_sec = active_ms / 1000.0
        res = ghost_distance_at_active_time(self._timeline, active_sec, clamp=True)
        return res.distanceM, res.paceSecPer100M

    def _display_from_timeline(self, timeline_distance_m: float) -> float:
        display = self._anchor.anchorDisplayDistanceM + (
            timeline_distance_m - self._anchor.anchorTimelineDistanceM
        )
        return min(max(display, 0.0), self._timeline.totalDistanceM)

    def _expected_wall_for(self, tracked_distance_m: float) -> float:
        # If already on a wall, that wall is the official boundary; else the next wall.
        if is_wall_boundary(tracked_distance_m, self._pool_length_m):
            return tracked_distance_m
        return next_wall_boundary(
            tracked_distance_m, self._pool_length_m, self._timeline.totalDistanceM
        )

    def _build_snapshot(self, now_ms: int) -> GhostSnapshot:
        snap = self._clock.snapshot(now_ms)
        timeline_distance, pace = self._timeline_distance_at_active(snap.activeElapsedMs)
        display = (
            self._anchor.anchorDisplayDistanceM
            if self._state is GhostState.STOP_PAUSED
            else self._display_from_timeline(timeline_distance)
        )
        return GhostSnapshot(
            state=self._state,
            wallElapsedMs=snap.wallElapsedMs,
            activeElapsedMs=snap.activeElapsedMs,
            stoppedElapsedMs=snap.stoppedElapsedMs,
            timelineDistanceM=timeline_distance,
            displayDistanceM=display,
            targetPaceSecPer100M=pace,
            alignmentActive=self._alignment_active,
            wallReconciliationPending=self._wall_reconciliation_pending,
            expectedReconciliationWallM=self._expected_reconciliation_wall_m,
        )

    @staticmethod
    def _check_finite(value: float, label: str) -> None:
        if not math.isfinite(value):
            raise InvalidAlignmentDistanceError(f"{label} must be finite, got {value}")

    # ---------------------------------------------------------------- API
    def snapshot(self, now_ms: int) -> GhostSnapshot:
        # ActiveClock enforces monotonic (non-historical) time; do not swallow that error.
        return self._build_snapshot(now_ms)

    def apply_stop_pause(
        self,
        stop_started_at_ms: int,
        confirmed_at_ms: int,
        tracked_alignment_distance_m: float,
    ) -> GhostSnapshot:
        if self._state is not GhostState.ACTIVE:
            raise InvalidGhostTransitionError("can only StopPause from ACTIVE state")
        if self._wall_reconciliation_pending:
            raise InvalidGhostTransitionError(
                "a previous alignment is still pending reconciliation"
            )
        self._check_finite(tracked_alignment_distance_m, "tracked_alignment_distance_m")
        if not (
            -_WALL_TOL <= tracked_alignment_distance_m <= self._timeline.totalDistanceM + _WALL_TOL
        ):
            raise InvalidAlignmentDistanceError(
                f"alignment distance {tracked_alignment_distance_m} out of "
                f"[0, {self._timeline.totalDistanceM}]"
            )
        tracked = min(max(tracked_alignment_distance_m, 0.0), self._timeline.totalDistanceM)
        # ActiveClock freeze must succeed BEFORE any ghost state change.
        self._clock.freeze_from(stop_started_at_ms, confirmed_at_ms)
        frozen_active_ms = self._clock.active_elapsed_ms(confirmed_at_ms)
        timeline_at_stop, _ = self._timeline_distance_at_active(frozen_active_ms)
        self._anchor = GhostAnchor(
            anchorActiveElapsedSec=frozen_active_ms / 1000.0,
            anchorTimelineDistanceM=timeline_at_stop,
            anchorDisplayDistanceM=tracked,
        )
        self._state = GhostState.STOP_PAUSED
        self._alignment_active = True
        self._wall_reconciliation_pending = True
        self._expected_reconciliation_wall_m = self._expected_wall_for(tracked)
        return self._build_snapshot(confirmed_at_ms)

    def resume_from_stop_pause(self, resumed_at_ms: int) -> GhostSnapshot:
        if self._state is not GhostState.STOP_PAUSED:
            raise InvalidGhostTransitionError("can only resume from STOP_PAUSED state")
        self._clock.resume(resumed_at_ms)
        self._state = GhostState.ACTIVE
        # alignment + pending reconciliation stay set until reconciled at the expected wall
        return self._build_snapshot(resumed_at_ms)

    def reconcile_at_wall(
        self,
        wall_distance_m: float,
        reconciled_at_ms: int,
    ) -> GhostSnapshot:
        if self._state is not GhostState.ACTIVE:
            raise InvalidWallReconciliationError("reconciliation requires ACTIVE state")
        if not self._wall_reconciliation_pending or self._expected_reconciliation_wall_m is None:
            raise InvalidWallReconciliationError("no pending StopPause alignment to reconcile")
        self._check_finite(wall_distance_m, "wall_distance_m")
        expected = self._expected_reconciliation_wall_m
        if abs(wall_distance_m - expected) > _WALL_TOL:
            raise InvalidWallReconciliationError(
                f"only the next valid wall {expected} may be reconciled, got {wall_distance_m}"
            )
        # Move only the ghost display anchor to the reconciled wall; no timeline/state mutation.
        current = self._build_snapshot(reconciled_at_ms)
        self._anchor = GhostAnchor(
            anchorActiveElapsedSec=current.activeElapsedMs / 1000.0,
            anchorTimelineDistanceM=current.timelineDistanceM,
            anchorDisplayDistanceM=wall_distance_m,
        )
        self._alignment_active = False
        self._wall_reconciliation_pending = False
        self._expected_reconciliation_wall_m = None
        return self._build_snapshot(reconciled_at_ms)

    def apply_coach_pacing_reset_at_wall(
        self,
        wall_distance_m: float,
        applied_at_ms: int,
    ) -> GhostSnapshot:
        """Move the display anchor to a wall for a coach pacing reset (not a StopPause).

        Pure: creates no StopPause, adds no stopped duration, does not freeze the active
        clock, and does not erase prior gap/split data. Only valid ACTIVE, at a real wall,
        with no pending StopPause reconciliation, leaving the timeline untouched and the
        current target-pace context intact.
        """
        if self._state is not GhostState.ACTIVE:
            raise InvalidWallReconciliationError("coach pacing reset requires ACTIVE state")
        if self._wall_reconciliation_pending:
            raise InvalidWallReconciliationError(
                "coach pacing reset not allowed while a StopPause reconciliation is pending"
            )
        self._check_finite(wall_distance_m, "wall_distance_m")
        if (
            wall_distance_m < -_WALL_TOL
            or wall_distance_m > self._timeline.totalDistanceM + _WALL_TOL
        ):
            raise InvalidWallReconciliationError(
                f"wall distance {wall_distance_m} out of [0, {self._timeline.totalDistanceM}]"
            )
        if not is_wall_boundary(wall_distance_m, self._pool_length_m):
            raise InvalidWallReconciliationError(
                f"{wall_distance_m} is not a wall boundary (pool {self._pool_length_m}); "
                "coach pacing reset must land on a wall (no mid-pool)"
            )
        current = self._build_snapshot(applied_at_ms)
        self._anchor = GhostAnchor(
            anchorActiveElapsedSec=current.activeElapsedMs / 1000.0,
            anchorTimelineDistanceM=current.timelineDistanceM,
            anchorDisplayDistanceM=wall_distance_m,
        )
        return self._build_snapshot(applied_at_ms)
