"""Per-segment linear pace curves and their exact (integral / inverse-quadratic) solutions.

Every supported mode reduces to a *linear* pace curve over segment-local distance ``x`` in
``[0, L]``::

    p(x) = p0 + (p1 - p0) * x / L        (sec/100m, smaller = faster)

- even_pace / negative_split_part: p0 = p1 = target
- controlled_start:                p0 = startPace (slower/equal), p1 = target
- progressive:                     p0 = target,   p1 = endPace (faster/equal)

Elapsed active time to local distance ``x`` is the integral of ``p(u)/100``::

    T(x) = (1/100) * [ p0*x + (p1 - p0) * x^2 / (2L) ]

so total duration is ``L * (p0 + p1) / 200``. The inverse ``x(T)`` is the physically valid
root of the resulting quadratic — never a linear time/distance-ratio approximation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swimcore.pacing.errors import InvalidPaceCurveError, UnsupportedPaceModeError
from swimcore.pacing.math import validate_pace
from swimcore.pacing.types import EPSILON

_EVEN = "even_pace"
_NEGATIVE_SPLIT = "negative_split_part"
_CONTROLLED_START = "controlled_start"
_PROGRESSIVE = "progressive"


@dataclass(frozen=True, slots=True)
class ControlledStartProfile:
    startPaceSecPer100M: float
    targetPaceSecPer100M: float


def resolve_curve_endpoints(
    mode: str,
    target_pace: float,
    start_pace: float | None,
    end_pace: float | None,
) -> tuple[float, float]:
    """Return the resolved ``(p0, p1)`` linear endpoints for a segment mode."""
    validate_pace(target_pace)
    if mode in (_EVEN, _NEGATIVE_SPLIT):
        return target_pace, target_pace
    if mode == _CONTROLLED_START:
        if start_pace is None:
            raise InvalidPaceCurveError("controlled_start requires startPaceSecPer100M")
        validate_pace(start_pace)
        return start_pace, target_pace
    if mode == _PROGRESSIVE:
        if end_pace is None:
            raise InvalidPaceCurveError("progressive requires endPaceSecPer100M")
        validate_pace(end_pace)
        return target_pace, end_pace
    raise UnsupportedPaceModeError(f"unsupported pace mode: {mode}")


def curve_duration(length_m: float, p0: float, p1: float) -> float:
    """Active duration over a full linear segment: ``L * (p0 + p1) / 200``."""
    if length_m < -EPSILON:
        raise InvalidPaceCurveError(f"segment length must be >= 0, got {length_m}")
    return max(length_m, 0.0) * (p0 + p1) / 200.0


def elapsed_at_local_distance(x: float, length_m: float, p0: float, p1: float) -> float:
    """``T(x)`` — active time to reach local distance ``x`` in ``[0, L]``."""
    if length_m <= EPSILON:
        return 0.0
    x = min(max(x, 0.0), length_m)
    return (p0 * x + (p1 - p0) * x * x / (2.0 * length_m)) / 100.0


def pace_at_local_distance(x: float, length_m: float, p0: float, p1: float) -> float:
    if length_m <= EPSILON:
        return p0
    x = min(max(x, 0.0), length_m)
    return p0 + (p1 - p0) * x / length_m


def local_distance_at_elapsed(t: float, length_m: float, p0: float, p1: float) -> float:
    """Inverse of :func:`elapsed_at_local_distance`: exact quadratic root in ``[0, L]``."""
    if length_m <= EPSILON or t <= 0.0:
        return 0.0
    total = curve_duration(length_m, p0, p1)
    if t >= total - EPSILON:
        return length_m
    a = (p1 - p0) / (2.0 * length_m)
    if abs(a) < EPSILON:
        # constant pace: x = 100 t / p0
        return min(max(100.0 * t / p0, 0.0), length_m)
    disc = p0 * p0 + 400.0 * a * t
    if disc < 0.0:  # pragma: no cover - guarded by t in (0, total)
        raise InvalidPaceCurveError("no real solution for inverse pace curve")
    root = math.sqrt(disc)
    for candidate in ((-p0 + root) / (2.0 * a), (-p0 - root) / (2.0 * a)):
        if -EPSILON <= candidate <= length_m + EPSILON:
            return min(max(candidate, 0.0), length_m)
    raise InvalidPaceCurveError("inverse pace-curve root outside segment")  # pragma: no cover
