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

from swimcore.pacing.errors import (
    InvalidDistanceError,
    InvalidDurationError,
    InvalidPaceCurveError,
    UnsupportedPaceModeError,
)
from swimcore.pacing.math import _finite, require_finite_result, validate_pace
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
    """Return the resolved ``(p0, p1)`` linear endpoints for a segment mode.

    The math layer faithfully reflects the given endpoints and only validates that each
    supplied pace is finite and present. Pace *direction* (controlled_start must start
    slower-or-equal; progressive must end faster-or-equal) is a semantic concern owned by
    the Commit-3 validator (RULE-004 and the controlled_start direction rule), so it is not
    re-enforced here — the compiler never applies a silent correction.
    """
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


def segment_active_duration_sec(
    mode: str,
    from_m: float,
    to_m: float,
    target_pace: float,
    start_pace: float | None = None,
    end_pace: float | None = None,
) -> float:
    """Single source of truth for a segment's active swim duration (sec).

    Shared by the pace timeline compiler *and* the semantic validator's rest-sanity rule so
    there is exactly one pace formula. May raise a ``PaceMathError`` on an invalid curve.
    """
    length = to_m - from_m
    if not _finite(length):
        raise InvalidPaceCurveError(f"segment length must be finite, got {length}")
    p0, p1 = resolve_curve_endpoints(mode, target_pace, start_pace, end_pace)
    return curve_duration(length, p0, p1)


def _require_finite_length(length_m: float) -> None:
    if not _finite(length_m):
        raise InvalidPaceCurveError(f"segment length must be finite, got {length_m}")
    if length_m <= 0.0:
        raise InvalidPaceCurveError(f"segment length must be > 0, got {length_m}")


def curve_duration(length_m: float, p0: float, p1: float) -> float:
    """Active duration over a full linear segment: ``L * (p0 + p1) / 200``."""
    _require_finite_length(length_m)
    validate_pace(p0)
    validate_pace(p1)
    return require_finite_result(length_m * (p0 + p1) / 200.0, "curve duration")


def elapsed_at_local_distance(x: float, length_m: float, p0: float, p1: float) -> float:
    """``T(x)`` — active time to reach local distance ``x`` in ``[0, L]``."""
    _require_finite_length(length_m)
    validate_pace(p0)
    validate_pace(p1)
    if not _finite(x):
        raise InvalidDistanceError(f"local distance must be finite, got {x}")
    if x < -EPSILON or x > length_m + EPSILON:
        raise InvalidDistanceError(f"local distance {x} out of [0, {length_m}]")
    x = min(max(x, 0.0), length_m)
    return require_finite_result(
        (p0 * x + (p1 - p0) * x * x / (2.0 * length_m)) / 100.0, "elapsed time"
    )


def pace_at_local_distance(x: float, length_m: float, p0: float, p1: float) -> float:
    _require_finite_length(length_m)
    validate_pace(p0)
    validate_pace(p1)
    if not _finite(x):
        raise InvalidDistanceError(f"local distance must be finite, got {x}")
    if x < -EPSILON or x > length_m + EPSILON:
        raise InvalidDistanceError(f"local distance {x} out of [0, {length_m}]")
    x = min(max(x, 0.0), length_m)
    return require_finite_result(p0 + (p1 - p0) * x / length_m, "pace")


def local_distance_at_elapsed(t: float, length_m: float, p0: float, p1: float) -> float:
    """Inverse of :func:`elapsed_at_local_distance`: exact quadratic root in ``[0, L]``."""
    _require_finite_length(length_m)
    validate_pace(p0)
    validate_pace(p1)
    if not _finite(t):
        raise InvalidDurationError(f"elapsed time must be finite, got {t}")
    total = curve_duration(length_m, p0, p1)
    if t < -EPSILON or t > total + EPSILON:
        raise InvalidDurationError(f"elapsed time {t} out of [0, {total}]")
    if t <= 0.0:
        return 0.0
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
