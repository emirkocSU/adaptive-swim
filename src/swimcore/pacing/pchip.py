"""Pure, deterministic, stdlib-only PCHIP interpolation (ADR-038).

Piecewise Cubic Hermite Interpolating Polynomial with Fritsch–Carlson shape-preserving
derivatives. No SciPy, no NumPy, no global state, no randomness, no I/O. The same knots
always yield the same coefficients and the same evaluations; the interpolant never
overshoots the local knot value range on a segment, and knot values are reproduced exactly.

This is the single authoritative curve evaluator (the simulator must not write its own).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_EPS = 1e-12


class PchipError(Exception):
    """A PCHIP curve could not be built or evaluated deterministically."""


def _finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


@dataclass(frozen=True, slots=True)
class PchipInterpolator:
    """An evaluatable monotone cubic Hermite interpolant over strictly increasing knots.

    ``xs`` strictly increasing; ``ys`` finite. ``derivatives`` are the Fritsch–Carlson
    shape-preserving slopes at each knot. Evaluation on ``[xs[i], xs[i+1]]`` uses the Hermite
    basis, so ``evaluate(xs[i]) == ys[i]`` exactly.
    """

    xs: tuple[float, ...]
    ys: tuple[float, ...]
    derivatives: tuple[float, ...]

    def evaluate(self, x: float) -> float:
        xs = self.xs
        if not _finite(x):
            raise PchipError(f"evaluation point must be finite, got {x}")
        n = len(xs)
        if x <= xs[0]:
            if x < xs[0] - 1e-9:
                raise PchipError(f"x {x} below curve domain [{xs[0]}, {xs[-1]}]")
            return self.ys[0]
        if x >= xs[-1]:
            if x > xs[-1] + 1e-9:
                raise PchipError(f"x {x} above curve domain [{xs[0]}, {xs[-1]}]")
            return self.ys[-1]
        # binary search for the interval [xs[i], xs[i+1]] containing x
        lo, hi = 0, n - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if xs[mid] <= x:
                lo = mid
            else:
                hi = mid
        return self._hermite(lo, x)

    def _hermite(self, i: int, x: float) -> float:
        h = self.xs[i + 1] - self.xs[i]
        t = (x - self.xs[i]) / h
        t2 = t * t
        t3 = t2 * t
        h00 = 2.0 * t3 - 3.0 * t2 + 1.0
        h10 = t3 - 2.0 * t2 + t
        h01 = -2.0 * t3 + 3.0 * t2
        h11 = t3 - t2
        y0, y1 = self.ys[i], self.ys[i + 1]
        m0, m1 = self.derivatives[i], self.derivatives[i + 1]
        value = h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1
        if not _finite(value):
            raise PchipError("PCHIP evaluation overflowed to a non-finite value")
        return value

    def derivative(self, x: float) -> float:
        """Analytic first derivative dy/dx (used for acceleration bound checks)."""
        xs = self.xs
        if not _finite(x):
            raise PchipError(f"derivative point must be finite, got {x}")
        n = len(xs)
        idx = 0
        if x <= xs[0]:
            idx = 0
        elif x >= xs[-1]:
            idx = n - 2
        else:
            lo, hi = 0, n - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if xs[mid] <= x:
                    lo = mid
                else:
                    hi = mid
            idx = lo
        h = xs[idx + 1] - xs[idx]
        t = min(max((x - xs[idx]) / h, 0.0), 1.0)
        t2 = t * t
        dh00 = 6.0 * t2 - 6.0 * t
        dh10 = 3.0 * t2 - 4.0 * t + 1.0
        dh01 = -6.0 * t2 + 6.0 * t
        dh11 = 3.0 * t2 - 2.0 * t
        y0, y1 = self.ys[idx], self.ys[idx + 1]
        m0, m1 = self.derivatives[idx], self.derivatives[idx + 1]
        value = (dh00 * y0 + dh01 * y1) / h + dh10 * m0 + dh11 * m1
        if not _finite(value):
            raise PchipError("PCHIP derivative overflowed to a non-finite value")
        return value


def _fritsch_carlson_slopes(xs: tuple[float, ...], ys: tuple[float, ...]) -> tuple[float, ...]:
    """Shape-preserving derivatives (Fritsch–Carlson, 1980). Deterministic."""
    n = len(xs)
    if n == 2:
        slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
        return (slope, slope)

    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    delta = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n

    # interior nodes: weighted harmonic mean when secants share sign, else zero (local extremum)
    for i in range(1, n - 1):
        if delta[i - 1] == 0.0 or delta[i] == 0.0 or (delta[i - 1] > 0.0) != (delta[i] > 0.0):
            m[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])

    # endpoints: non-centered three-point formula with monotonicity guard (shape-preserving)
    m[0] = _endpoint_slope(h[0], h[1], delta[0], delta[1])
    m[-1] = _endpoint_slope(h[-1], h[-2], delta[-1], delta[-2])
    return tuple(m)


def _endpoint_slope(h0: float, h1: float, d0: float, d1: float) -> float:
    slope = ((2.0 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    # clamp to preserve monotonicity/shape at the boundary
    if (slope > 0.0) != (d0 > 0.0) and d0 != 0.0:
        slope = 0.0
    elif (d0 > 0.0) != (d1 > 0.0) and abs(slope) > 3.0 * abs(d0):
        slope = 3.0 * d0
    return slope


def build_pchip(
    distances: tuple[float, ...],
    values: tuple[float, ...],
) -> PchipInterpolator:
    """Build a deterministic monotone cubic Hermite interpolant.

    ``distances`` must be strictly increasing and finite; ``values`` finite. Raises
    :class:`PchipError` on any degenerate input.
    """
    if len(distances) != len(values):
        raise PchipError("distances and values must have equal length")
    if len(distances) < 2:
        raise PchipError("PCHIP needs at least two knots")
    for d in distances:
        if not _finite(d):
            raise PchipError(f"knot distance must be finite, got {d}")
    for v in values:
        if not _finite(v):
            raise PchipError(f"knot value must be finite, got {v}")
    for i in range(len(distances) - 1):
        if distances[i + 1] <= distances[i] + _EPS:
            raise PchipError(
                f"knot distances must be strictly increasing: "
                f"{distances[i]} then {distances[i + 1]}"
            )
    derivatives = _fritsch_carlson_slopes(distances, values)
    return PchipInterpolator(xs=distances, ys=values, derivatives=derivatives)
