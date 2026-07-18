"""Ghost primitive: drives the compiled pace timeline by active time.

Pure and clock-injected. Aligns to an externally supplied tracked point only during a
confirmed StopPause; never estimates swimmer position, never performs I/O.
"""

from __future__ import annotations

from swimcore.ghost.clock import GhostClock
from swimcore.ghost.errors import (
    GhostError,
    InvalidAlignmentDistanceError,
    InvalidGhostTransitionError,
    InvalidWallReconciliationError,
)
from swimcore.ghost.types import GhostAnchor, GhostSnapshot, GhostState

__all__ = [
    "GhostClock",
    "GhostAnchor",
    "GhostSnapshot",
    "GhostState",
    "GhostError",
    "InvalidAlignmentDistanceError",
    "InvalidGhostTransitionError",
    "InvalidWallReconciliationError",
]
