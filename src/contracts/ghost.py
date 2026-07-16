"""Ghost operational contracts (StopPause model).

Rules:
- Normal / large pace loss → ghost stays ``ACTIVE`` (``CONTINUE_PLAN``).
- Verified StopPause → ghost may align to the swimmer's currently tracked point
  (``CONTROLLED_STOP_PAUSE_ALIGNMENT``) and wait; official accounting is reconciled at the
  next wall.
- Coach pacing reset is a separate behaviour (``COACH_PACING_RESET_AT_WALL``); it is NOT a
  StopPause.
"""

from __future__ import annotations

from contracts._base import StrictModel
from contracts.enums import GhostAlignmentMode, GhostOperationalState


class GhostReference(StrictModel):
    """Deterministic anchor for the ghost clock; the ghost position is never persisted,
    it is derived from this reference and the event chain."""

    t0Ms: int
    cumulativeStoppedMs: int = 0
    planClockOffsetMs: int = 0
    operationalState: GhostOperationalState = GhostOperationalState.ACTIVE
    alignmentMode: GhostAlignmentMode = GhostAlignmentMode.CONTINUE_PLAN
    #: While STOP_PAUSED, the frozen ghost distance the ghost waits at (may be mid-pool).
    alignedAtDistanceM: float | None = None
    #: True when a controlled alignment happened mid-pool and wall reconciliation is due.
    pendingWallReconciliation: bool = False
