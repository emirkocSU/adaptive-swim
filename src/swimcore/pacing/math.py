"""Constant-pace formulas and numeric guards.

Convention: pace is sec/100m, smaller = faster. All functions are pure and reject NaN /
infinity. No rounding, no formatting.
"""

from __future__ import annotations

import math

from swimcore.pacing.errors import (
    InvalidDistanceError,
    InvalidDurationError,
    InvalidPaceCurveError,
    InvalidPaceError,
)
from swimcore.pacing.types import EPSILON


def _finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


def require_finite_result(value: float, label: str = "result") -> float:
    """Guarantee a public function never returns NaN/inf even for huge finite inputs."""
    if not _finite(value):
        raise InvalidPaceCurveError(
            f"{label} overflowed to a non-finite value; inputs exceed the supported range"
        )
    return value


def validate_pace(pace_sec_per_100m: float) -> float:
    if not _finite(pace_sec_per_100m):
        raise InvalidPaceError(f"pace must be finite, got {pace_sec_per_100m}")
    if pace_sec_per_100m <= 0:
        raise InvalidPaceError(f"pace must be > 0, got {pace_sec_per_100m}")
    return pace_sec_per_100m


def validate_distance(distance_m: float) -> float:
    if not _finite(distance_m):
        raise InvalidDistanceError(f"distance must be finite, got {distance_m}")
    if distance_m < -EPSILON:
        raise InvalidDistanceError(f"distance must be >= 0, got {distance_m}")
    return max(distance_m, 0.0)


def validate_duration(duration_sec: float) -> float:
    if not _finite(duration_sec):
        raise InvalidDurationError(f"duration must be finite, got {duration_sec}")
    if duration_sec < -EPSILON:
        raise InvalidDurationError(f"duration must be >= 0, got {duration_sec}")
    return max(duration_sec, 0.0)


def duration_for_distance(distance_m: float, pace_sec_per_100m: float) -> float:
    """``d * p / 100``. Zero distance → zero duration."""
    distance_m = validate_distance(distance_m)
    pace = validate_pace(pace_sec_per_100m)
    return require_finite_result(distance_m * pace / 100.0, "duration")


def distance_for_duration(duration_sec: float, pace_sec_per_100m: float) -> float:
    """``t * 100 / p``. Zero duration → zero distance."""
    duration_sec = validate_duration(duration_sec)
    pace = validate_pace(pace_sec_per_100m)
    return require_finite_result(duration_sec * 100.0 / pace, "distance")
