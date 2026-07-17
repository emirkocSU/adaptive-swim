"""Immutable ghost domain types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GhostState(StrEnum):
    ACTIVE = "ACTIVE"
    STOP_PAUSED = "STOP_PAUSED"


@dataclass(frozen=True, slots=True)
class GhostAnchor:
    """Continuity anchor so the ghost never jumps back to its old planned position.

    ``displayDistanceM = anchorDisplayDistanceM
                          + (timelineDistance(currentActiveTime) - anchorTimelineDistanceM)``
    """

    anchorActiveElapsedSec: float
    anchorTimelineDistanceM: float
    anchorDisplayDistanceM: float


@dataclass(frozen=True, slots=True)
class GhostSnapshot:
    state: GhostState
    wallElapsedMs: int
    activeElapsedMs: int
    stoppedElapsedMs: int
    #: Mathematical position on the unchanging workout plan timeline.
    timelineDistanceM: float
    #: Ghost position after any temporary alignment offset is applied.
    displayDistanceM: float
    targetPaceSecPer100M: float
    alignmentActive: bool
    #: True between a confirmed StopPause alignment and its single wall reconciliation.
    wallReconciliationPending: bool = False
    #: The one wall distance at which this pending alignment may be reconciled.
    expectedReconciliationWallM: float | None = None
