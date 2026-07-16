"""Deterministic pace-math engine (Commit 4).

Pure, side-effect-free, clock-independent active-swimming pace mathematics. Converts a
workout plan into a distance/active-time target pace timeline. Rest, StopPause, and real
elapsed time are **not** part of this layer.
"""

from swimcore.pacing.curves import ControlledStartProfile, resolve_curve_endpoints
from swimcore.pacing.errors import (
    DistanceOutsideTimelineError,
    InvalidDistanceError,
    InvalidDurationError,
    InvalidPaceCurveError,
    InvalidPaceError,
    PaceMathError,
    TimeOutsideTimelineError,
    UnsupportedPaceModeError,
)
from swimcore.pacing.math import distance_for_duration, duration_for_distance
from swimcore.pacing.timeline import (
    compile_pace_timeline,
    ghost_distance_at_active_time,
    is_wall_boundary,
    next_wall_boundary,
    previous_wall_boundary,
    target_active_time_at_distance,
)
from swimcore.pacing.types import (
    EPSILON,
    DistanceAtTimeResult,
    PaceInterval,
    PacePoint,
    PaceTimeline,
    TimeAtDistanceResult,
)

__all__ = [
    "EPSILON",
    "ControlledStartProfile",
    "DistanceAtTimeResult",
    "DistanceOutsideTimelineError",
    "InvalidDistanceError",
    "InvalidDurationError",
    "InvalidPaceCurveError",
    "InvalidPaceError",
    "PaceInterval",
    "PaceMathError",
    "PacePoint",
    "PaceTimeline",
    "TimeAtDistanceResult",
    "TimeOutsideTimelineError",
    "UnsupportedPaceModeError",
    "compile_pace_timeline",
    "distance_for_duration",
    "duration_for_distance",
    "ghost_distance_at_active_time",
    "is_wall_boundary",
    "next_wall_boundary",
    "previous_wall_boundary",
    "resolve_curve_endpoints",
    "target_active_time_at_distance",
]
